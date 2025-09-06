# Correct code for rl_agent.py

import random
import numpy as np
import pickle
import os

class QLearningAgent:
    def __init__(self, actions, learning_rate=0.1, discount_factor=0.9, epsilon=0.1):
        self.actions = actions
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.epsilon = epsilon
        self.q_table = {}
        self.q_table_path = 'q_table.pkl'
        self.load_q_table()

    def get_q_value(self, state, action):
        """Retrieve the Q-value from the table, defaulting to 0."""
        return self.q_table.get((state, action), 0.0)

    def choose_action(self, state):
        """
        Choose an action using an epsilon-greedy strategy.
        """
        if random.uniform(0, 1) < self.epsilon:
            return random.choice(self.actions)
        else:
            q_values = [self.get_q_value(state, a) for a in self.actions]
            max_q = max(q_values)
            best_actions_indices = [i for i, q in enumerate(q_values) if q == max_q]
            chosen_action_index = random.choice(best_actions_indices)
            return self.actions[chosen_action_index]

    def update(self, state, action, reward, next_state):
        """
        Update the Q-table using the Bellman equation.
        """
        old_q = self.get_q_value(state, action)
        future_q = max([self.get_q_value(next_state, a) for a in self.actions])
        new_q = old_q + self.alpha * (reward + self.gamma * future_q - old_q)
        self.q_table[(state, action)] = new_q
    
    def load_q_table(self):
        """Loads the Q-table from a file if it exists."""
        if os.path.exists(self.q_table_path):
            with open(self.q_table_path, 'rb') as f:
                self.q_table = pickle.load(f)
            print("Q-table loaded successfully.")
        else:
            print("No existing Q-table found. Starting fresh.")

    def save_q_table(self):
        """Saves the Q-table to a file."""
        with open(self.q_table_path, 'wb') as f:
            pickle.dump(self.q_table, f)
        print(f"Q-table saved to {self.q_table_path}")

    def decay_epsilon(self, min_epsilon=0.05, decay_rate=0.9995):
        """Gradually reduce the exploration rate."""
        if self.epsilon > min_epsilon:
            self.epsilon *= decay_rate