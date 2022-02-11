# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.help_files import helps  # pylint: disable=unused-import


helps['containerapp'] = """
    type: group
    short-summary: Commands to manage Containerapps.
"""

helps['containerapp create'] = """
    type: command
    short-summary: Create a Containerapp.
"""

helps['containerapp show'] = """
    type: command
    short-summary: Show details of a Containerapp.
    examples:
    - name: Show the details of a Containerapp.
      text: |
          az containerapp show -n MyContainerapp -g MyResourceGroup
"""

helps['containerapp list'] = """
    type: command
    short-summary: List Containerapps.
    examples:
    - name: List Containerapps by subscription.
      text: |
          az containerapp list
    - name: List Containerapps by resource group.
      text: |
          az containerapp list -g MyResourceGroup
"""

# Environment Commands
helps['containerapp env'] = """
    type: group
    short-summary: Commands to manage Containerapp environments.
"""

helps['containerapp env create'] = """
    type: command
    short-summary: Create a Containerapp environment.
    examples:
    - name: Create a Containerapp Environment.
      text: |
          az containerapp env create -n MyContainerappEnvironment -g MyResourceGroup \\
              --logs-workspace-id myLogsWorkspaceID \\
              --logs-workspace-key myLogsWorkspaceKey \\
              --location Canada Central
"""

helps['containerapp env update'] = """
    type: command
    short-summary: Update a Containerapp environment. Currently Unsupported.
"""

helps['containerapp env delete'] = """
    type: command
    short-summary: Deletes a Containerapp Environment.
    examples:
    - name: Delete Containerapp Environment.
      text: az containerapp env delete -g MyResourceGroup -n MyContainerappEnvironment
"""

helps['containerapp env show'] = """
    type: command
    short-summary: Show details of a Containerapp environment.
    examples:
    - name: Show the details of a Containerapp Environment.
      text: |
          az containerapp env show -n MyContainerappEnvironment -g MyResourceGroup
"""

helps['containerapp env list'] = """
    type: command
    short-summary: List Containerapp environments by subscription or resource group.
    examples:
    - name: List Containerapp Environments by subscription.
      text: |
          az containerapp env list
    - name: List Containerapp Environments by resource group.
      text: |
          az containerapp env list -g MyResourceGroup
"""
