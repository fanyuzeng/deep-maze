import pygame
from skimage import color, transform, exposure
from math import ceil
import numpy as np
from maze import Maze
from pathfinding import dfs
from mechanics import NormalMaze


class Sprite(pygame.sprite.DirtySprite):
    def __init__(self, color, x, y, w, h):
        pygame.sprite.DirtySprite.__init__(self)
        self.w = w
        self.h = h
        self.image = pygame.Surface((w, h))
        self.image.fill(color)
        self.rect = self.image.get_rect()
        self.move(x, y)

        self.original_color = color

    def set_color(self, color):
        self.image.fill(color)
        self.dirty = 1

    def move(self, x, y):
        self.rect.x = x * self.w
        self.rect.y = y * self.h
        self.dirty = 1


class MazeGame:

    def __init__(self, maze_size,
                 screen_size=(640, 480),
                 mechanic=NormalMaze,
                 mechanic_args=None,
                 colors=None,
                 ):
        #############################################################
        ##
        # Input Manipulation
        ##
        #############################################################
        mechanic_args = {} if mechanic_args is None else mechanic_args
        colors = {} if colors is None else colors

        #############################################################
        ##
        # Pygame Initialization
        ##
        #############################################################
        pygame.init()
        pygame.font.init()
        pygame.display.set_caption("DeepMaze")

        #############################################################
        ##
        # Game Dimensions & Configuration
        ##
        #############################################################
        self.width, self.height = maze_size
        self.tile_width, self.tile_height = ceil(screen_size[0] / maze_size[0]), ceil(screen_size[1] / maze_size[1])
        self.colors = dict(
            goal=(255, 0, 0),
            player=(0, 255, 0),
            wall=(255, 255, 255),
            floor=(0, 0, 0)
        )
        self.colors.update(colors)

        #############################################################
        ##
        # Pygame & Surface & Window
        ##
        #############################################################
        self.screen = pygame.display.set_mode(screen_size, 0, 32)
        self.surface = pygame.Surface(self.screen.get_size()).convert()
        self.font = pygame.font.SysFont("Arial", size=16)

        #############################################################
        ##
        # Sprite Definition
        ##
        #############################################################
        self.sprite_maze = [Sprite(color=(0, 0, 0), x=x, w=self.tile_width, y=y, h=self.tile_height) for y in
                            range(self.width) for x in range(self.height)]
        self.sprite_player = Sprite(color=(0, 255, 0), x=0, y=0, w=self.tile_width, h=self.tile_height)
        self.sprite_target = Sprite(color=(255, 0, 0), x=0, y=0, w=self.tile_width, h=self.tile_height)
        self.sprites = pygame.sprite.LayeredUpdates(self.sprite_maze, [self.sprite_target, self.sprite_player])
        self.rectangles = []

        #############################################################
        ##
        # Maze Definition
        ##
        #############################################################
        self.maze = None
        self.maze_optimal_path = None
        self.maze_optimal_path_length = None

        #############################################################
        ##
        # Player & Target Definition
        ##
        #############################################################
        self.player, self.target = None, None
        self.player_steps = None
        self.terminal = None

        #############################################################
        ##
        # Game Mechanics
        ##
        #############################################################
        self.mechanic = mechanic(self, **mechanic_args)

        #############################################################
        ##
        # Pre-processing
        ##
        #############################################################
        self.preprocess_image = None
        self.preprocess_resize = None
        self.preprocess_grayscale = None
        self.set_preprocess(None)

        # Reset the game
        self.reset()

    def set_preprocess(self, preprocess=None):
        preprocess = dict(
            image=dict(),
            resize=dict(size=(84, 84)),
            grayscale=dict()
        ) if preprocess is None else preprocess

        self.preprocess_image = True if "image" in preprocess else None
        self.preprocess_resize = preprocess["resize"]["size"] if "resize" in preprocess else None
        self.preprocess_grayscale = True if "grayscale" in preprocess else None

    def get_state(self):

        if self.preprocess_image:
            state = pygame.surfarray.pixels3d(self.surface)

            if self.preprocess_resize is not None:
                state = transform.resize(state, self.preprocess_resize, mode='constant')

            if self.preprocess_grayscale is not None:
                state = color.rgb2gray(state)

            state = state[:, ::-1]
        else:
            state = np.array(self.maze.grid, copy=True)
            state[self.player[0], self.player[1]] = 2
            state[self.target[0], self.target[1]] = 3
            state *= 255
        return state

    def reset(self):
        # Create new maze
        self.maze = Maze(width=self.width, height=self.height)

        # Update sprite color reflecting the maze state
        for i in range(self.width * self.height):
            x = i % self.width
            y = int((i - x) / self.width)

            sprite = self.sprites.get_sprite(i)
            color = self.colors["wall"] if self.maze.grid[x, y] == 0 else self.colors["floor"]
            sprite.set_color(color)
            sprite.original_color = color

        # Set player positions
        self.player, self.target = self.spawn_players()

        # Calculate shortest path
        self.maze_optimal_path = dfs(self, self.player, self.target)
        self.maze_optimal_path_length = self.maze_optimal_path[0]

        # Update player sprites
        self.sprite_player.move(*self.player)
        self.sprite_target.move(*self.target)

        # Update according to mechanic spec
        self.mechanic.on_start()

        # Reset the terminal state
        self.terminal = False

        # Reset Player step to 0
        self.player_steps = 0

        # Return state
        return self.get_state()

    def spawn_players(self):
        """
        Returns a random position on the maze.
        """
        start_positions = []
        for start_position in [(0, 0), (self.width - 1, self.height - 1)]:
            visited, queue = set(), [start_position]
            while queue:
                vertex = queue.pop(0)

                if self.maze.grid[vertex[0], vertex[1]] == 0:
                    start_positions.append(vertex)
                    queue.clear()
                    continue
                if vertex not in visited:
                    visited.add(vertex)
                    queue.extend(self.maze.grid[vertex[0], vertex[1]] - visited)

        return start_positions

    def render(self):
        if not self.preprocess_image:
            self.rectangles = self.sprites.draw(self.surface)
        self.screen.blit(self.surface, (0, 0))
        pygame.display.update(self.rectangles)

    def on_return(self, reward):
        return self.get_state(), reward, self.terminal, dict(
            optimal_steps=self.maze_optimal_path_length,
            step_count=self.player_steps
        )

    def step(self, a):
        r = 0
        if self.terminal:
            r = 1
        else:
            dx, dy = MazeGame.to_action(a)
            x, y = self.player
            next_x, next_y = x + dx, y + dy

        if self.is_legal(next_x, next_y):
            self.player = (next_x, next_y)
            self.player_steps += 1
            self.sprite_player.move(*self.player)
            self.mechanic.on_update()

            if self.preprocess_image:
                self.rectangles = self.sprites.draw(self.surface)

        if self.player == self.target:
            self.terminal = True
            self.mechanic.on_terminal()
            r = 1
        else:
            r = -0.01

        return self.on_return(r)

    def quit(self):
        try:
            pygame.display.quit()
            pygame.quit()
        except:
            pass

    @staticmethod
    def to_action(a):
        if a == 0:
            return 0, 1
        elif a == 1:
            return 0, -1
        elif a == 2:
            return -1, 0
        elif a == 3:
            return 1, 0
        else:
            raise RuntimeError("Action must be a integer value between 0 and 3")

    def is_legal(self, x, y):
        return True if 0 <= x < self.width and 0 <= y < self.height and self.maze.grid[x, y] == 0 else False

    def legal_directions(self, x, y):
        legal = []

        possible_moves = [
            (x, y + 1),  # Down
            (x, y - 1),  # Up
            (x + 1, y),  # Left
            (x - 1, y)  # Right
        ]

        for x, y in possible_moves:
            if 0 <= x < self.width and 0 <= y < self.height and self.maze.grid[x, y] == 0:
                legal.append((x, y))

        return legal
