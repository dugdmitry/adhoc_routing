#!/usr/bin/python

"""
Created on Jun 17, 2016

@author: Dmitrii Dugaev


This module provides methods for selecting the actions and calculating their estimation values, according to the
Reinforcement Learning (RL) methodology, which came from the subject of Artificial Intelligence (AI) algorithms.
The abstract task of such algorithms is, based on current "situation" (a set of current possible actions and their
action "values"), select an optimal actions which will return the maximum possible reward.
Therefore, there are two input parameters which are required - a set of current actions, and the "feedback" from
each action in a form of "reward value". The underlying mechanism of action selection depends on the implemented
selection method, which could be a simple "greedy" algorithm, or more sophisticated "soft-max" solutions.
The other important values - are the "estimation" (or "estimated reward") values - which represent a predicted "outcome"
from the given action if this action would have been taken. The way those values are being estimated is the other
important task, which would affect the chosen action. They could be based, for example, on a simple "sample average"
calculation.
More information about the selection and calculation methods in RL can be found in R.Sutton's book:
"Reinforcement Learning: An Introduction"

The module has two main classes - ValueEstimator and ActionSelector.
The ValueEstimator class provides methods for estimating the current action values based on the last given reward which
has been received by selecting the action.
The ActionSelector class provides methods for selecting the action based on the given list of actions and their current
estimation values.
"""

import random


# Class for assigning current estimated value for a given action.
# Provides method for returning this value.
class ValueEstimator:
    def __init__(self, est_method_id="sample_average"):
        # Store current action ids and their current estimated value and step: {action_id: [est_value, step_count]}
        self.actions = dict()
        # Override the default method
        if est_method_id == "sample_average":
            self.estimate_value = self.estimate_value_by_sample_average
        else:
            self.estimate_value = self.estimate_value_by_sample_average

    def estimate_value(self):
        """
        Main method which returns current estimated value. It is overridden in the init().
        Input: action_id - some action identifier; reward - value of the assigned reward.
        Output: current estimated value.
        """
        pass

    # Estimate value by using a simple "sample average" method.
    # Reference to the method can be found in R.Sutton's book: Reinforcement Learning: An Introduction
    def estimate_value_by_sample_average(self, action_id, reward):
        if action_id not in self.actions:
            # Assign initial values
            self.actions.update({action_id: [0.0, 0]})

        # Calculate the estimated value
        estimated_value = (self.actions[action_id][0] * self.actions[action_id][1] + reward) \
                          / (self.actions[action_id][1] + 1)
        # Round it up
        estimated_value = round(estimated_value, 2)
        # Update the value
        self.actions[action_id][0] = estimated_value
        # Increment the counter
        self.actions[action_id][1] += 1
        # Return the value
        return estimated_value

    # Delete an action_id from the current actions list
    def delete_action_id(self, action_id):
        if action_id in self.actions:
            del self.actions[action_id]


# Class for selecting the action from the list of actions and their corresponding values.
# The interface is provided via select_action() method.
class ActionSelector:
    def __init__(self, selection_method_id="greedy"):
        # Override the default method
        if selection_method_id == "greedy":
            self.select_action = self.select_action_greedy

        elif selection_method_id == "e-greedy":
            # Set some parameters of e-greedy method
            self.eps = 0.1
            self.select_action = self.select_action_e_greedy

        elif selection_method_id == "soft-max":
            self.select_action = self.select_action_softmax

        else:
            self.select_action = self.select_action_greedy

    def select_action(self):
        """
        Default method for selecting the action. It is overridden in init().
        Input: {action_id: value}
        Output: action_id
        """
        pass

    # Select an action using "greedy" algorithm
    def select_action_greedy(self, action_values):
        if len(action_values) == 0:
            return None
        # Simply return the action_id with the maximum value
        return max(action_values, key=action_values.get)

    # Select an action using "e-greedy" algorithm
    def select_action_e_greedy(self, action_values):
        if len(action_values) == 0:
            return None
        # In (eps * 100) percent of cases, select an action with maximum value (use greedy method)
        # Otherwise, choose some other random action.
        greedy_action_id = self.select_action_greedy(action_values)
        if random.random() > self.eps:
            return greedy_action_id
        else:
            # Randomly choose some other action
            chosen_action_id = random.choice(action_values.keys())
            # Check the the selected action is not the "greedy" choice
            while action_values[chosen_action_id] == greedy_action_id and len(action_values) != 1:
                chosen_action_id = random.choice(action_values.keys())
            return chosen_action_id

    # Select an action using "soft-max" algorithm. It is based on Gibbs (Boltzmann) distribution.
    # See the reference in R.Sutton's book: Reinforcement Learning: An Introduction.
    def select_action_softmax(self, action_values):
        if len(action_values) == 0:
            return None
        # TODO: implement soft-max selection here.
        pass
