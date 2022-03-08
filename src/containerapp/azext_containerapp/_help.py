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
    examples:
    - name: Create a Containerapp
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage -e MyContainerappEnv \\
              --query properties.configuration.ingress.fqdn
    - name: Create a Containerapp with secrets and environment variables
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage -e MyContainerappEnv \\
              --secrets mysecret=escapefromtarkov,anothersecret=isadifficultgame \\
              --environment-variables myenvvar=foo,anotherenvvar=bar \\
              --query properties.configuration.ingress.fqdn
    - name: Create a Containerapp that only accepts internal traffic
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage -e MyContainerappEnv \\
              --ingress internal \\
              --query properties.configuration.ingress.fqdn
    - name: Create a Containerapp using an image from a private registry
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage -e MyContainerappEnv \\
              --secrets mypassword=verysecurepassword \\
              --registry-login-server MyRegistryServerAddress \\
              --registry-username MyUser \\
              --registry-password mypassword \\
              --query properties.configuration.ingress.fqdn
    - name: Create a Containerapp with a specified startup command and arguments
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage  -e MyContainerappEnv \\
              --command "/bin/sh" \\
              --args "-c", "while true; do echo hello; sleep 10;done" \\
              --query properties.configuration.ingress.fqdn
    - name: Create a Containerapp with a minimum resource and replica requirements
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage -e MyContainerappEnv \\
              --cpu 0.5 --memory 1.0Gi \\
              --min-replicas 4 --max-replicas 8 \\
              --query properties.configuration.ingress.fqdn
    - name: Create a Containerapp using a YAML configuration. Example YAML configuration - https://docs.microsoft.com/azure/container-apps/azure-resource-manager-api-spec#examples
      text: |
          az containerapp create -n MyContainerapp -g MyResourceGroup \\
              --yaml "C:/path/to/yaml/file.yml"
"""

helps['containerapp update'] = """
    type: command
    short-summary: Update a Containerapp.
    examples:
    - name: Update a Containerapp's container image
      text: |
          az containerapp update -n MyContainerapp -g MyResourceGroup \\
              --image MyNewContainerImage
    - name: Update a Containerapp with secrets and environment variables
      text: |
          az containerapp update -n MyContainerapp -g MyResourceGroup \\
              --secrets mysecret=secretfoo,anothersecret=secretbar
              --environment-variables myenvvar=foo,anotherenvvar=secretref:mysecretname
    - name: Update a Containerapp's ingress setting to internal
      text: |
          az containerapp update -n MyContainerapp -g MyResourceGroup \\
              --ingress internal
    - name: Update a Containerapp using an image from a private registry
      text: |
          az containerapp update -n MyContainerapp -g MyResourceGroup \\
              --image MyNewContainerImage \\
              --secrets mypassword=verysecurepassword \\
              --registry-login-server MyRegistryServerAddress \\
              --registry-username MyUser \\
              --registry-password mypassword
    - name: Update a Containerapp using a specified startup command and arguments
      text: |
          az containerapp update -n MyContainerapp -g MyResourceGroup \\
              --image MyContainerImage \\
              --command "/bin/sh"
              --args "-c", "while true; do echo hello; sleep 10;done"
    - name: Update a Containerapp with a minimum resource and replica requirements
      text: |
          az containerapp update -n MyContainerapp -g MyResourceGroup \\
              --cpu 0.5 --memory 1.0Gi \\
              --min-replicas 4 --max-replicas 8
"""

helps['containerapp delete'] = """
    type: command
    short-summary: Delete a Containerapp.
    examples:
    - name: Delete a Containerapp.
      text: az containerapp delete -g MyResourceGroup -n MyContainerapp
"""

helps['containerapp scale'] = """
    type: command
    short-summary: Set the min and max replicas for a Containerapp.
    examples:
    - name: Scale a Containerapp.
      text: az containerapp scale -g MyResourceGroup -n MyContainerapp --min-replicas 1 --max-replicas 2
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

# Revision Commands
helps['containerapp revision'] = """
    type: group
    short-summary: Commands to manage a Containerapp's revisions.
"""

helps['containerapp revision show'] = """
    type: command
    short-summary: Show details of a Containerapp's revision.
    examples:
    - name: Show details of a Containerapp's revision.
      text: |
          az containerapp revision show --revision-name MyContainerappRevision -g MyResourceGroup
"""

helps['containerapp revision list'] = """
    type: command
    short-summary: List details of a Containerapp's revisions.
    examples:
    - name: List a Containerapp's revisions.
      text: |
          az containerapp revision list --revision-name MyContainerapp -g MyResourceGroup
"""

helps['containerapp revision restart'] = """
    type: command
    short-summary: Restart a Containerapps's revision.
    examples:
    - name: Restart a Containerapp's revision.
      text: |
          az containerapp revision restart --revision-name MyContainerappRevision -g MyResourceGroup
"""

helps['containerapp revision activate'] = """
    type: command
    short-summary: Activates Containerapp's revision.
    examples:
    - name: Activate a Containerapp's revision.
      text: |
          az containerapp revision activate --revision-name MyContainerappRevision -g MyResourceGroup
"""

helps['containerapp revision deactivate'] = """
    type: command
    short-summary: Deactivates Containerapp's revision.
    examples:
    - name: Deactivate a Containerapp's revision.
      text: |
          az containerapp revision deactivate --revision-name MyContainerappRevision -g MyResourceGroup
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
    - name: Create a Containerapp Environment with an autogenerated Log Analytics
      text: |
          az containerapp env create -n MyContainerappEnvironment -g MyResourceGroup \\
              -- location Canada Central
    - name: Create a Containerapp Environment with Log Analytics
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
    short-summary: Delete a Containerapp Environment.
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
helps['containerapp github-action add'] = """
    type: command
    short-summary: Adds GitHub Actions to the Containerapp
    examples:
    - name: Add GitHub Actions, using Azure Container Registry and personal access token.
      text: az containerapp github-action add -g MyResourceGroup -n MyContainerapp --repo-url https://github.com/userid/repo --branch main
          --registry-url myregistryurl.azurecr.io
          --service-principal-client-id 00000000-0000-0000-0000-00000000
          --service-principal-tenant-id 00000000-0000-0000-0000-00000000
          --service-principal-client-secret ClientSecret
          --token MyAccessToken
    - name: Add GitHub Actions, using Azure Container Registry and log in to GitHub flow to retrieve personal access token.
      text: az containerapp github-action add -g MyResourceGroup -n MyContainerapp --repo-url https://github.com/userid/repo --branch main
          --registry-url myregistryurl.azurecr.io
          --service-principal-client-id 00000000-0000-0000-0000-00000000
          --service-principal-tenant-id 00000000-0000-0000-0000-00000000
          --service-principal-client-secret ClientSecret
          --login-with-github
    - name: Add GitHub Actions, using Dockerhub and log in to GitHub flow to retrieve personal access token.
      text: az containerapp github-action add -g MyResourceGroup -n MyContainerapp --repo-url https://github.com/userid/repo --branch main
          --registry-username MyUsername
          --registry-password MyPassword
          --service-principal-client-id 00000000-0000-0000-0000-00000000
          --service-principal-tenant-id 00000000-0000-0000-0000-00000000
          --service-principal-client-secret ClientSecret
          --login-with-github
"""

helps['containerapp github-action delete'] = """
    type: command
    short-summary: Removes GitHub Actions from the Containerapp
    examples:
    - name: Removes GitHub Actions, personal access token.
      text: az containerapp github-action delete -g MyResourceGroup -n MyContainerapp
          --token MyAccessToken
    - name: Removes GitHub Actions, using log in to GitHub flow to retrieve personal access token.
      text: az containerapp github-action delete -g MyResourceGroup -n MyContainerapp
          --login-with-github
"""

helps['containerapp github-action show'] = """
    type: command
    short-summary: Show the GitHub Actions configuration on a Containerapp
    examples:
    - name: Show the GitHub Actions configuration on a Containerapp
      text: az containerapp github-action show -g MyResourceGroup -n MyContainerapp
"""