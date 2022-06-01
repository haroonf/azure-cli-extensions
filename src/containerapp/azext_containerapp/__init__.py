# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=super-with-arguments

from azure.cli.core import AzCommandsLoader

from azext_containerapp._help import helps  # pylint: disable=unused-import
from azext_containerapp._client_factory import app_client_factory

class ContainerappCommandsLoader(AzCommandsLoader):

    def __init__(self, cli_ctx=None):
        from azure.cli.core.commands import CliCommandType
        from azure.cli.core.profiles import ResourceType

        containerapp_custom = CliCommandType(
            operations_tmpl='azext_containerapp.custom#{}',
            client_factory=app_client_factory)
        super(ContainerappCommandsLoader, self).__init__(cli_ctx=cli_ctx,
                                                         custom_command_type=containerapp_custom,
                                                         resource_type=ResourceType.MGMT_APPCONTAINERS)

    def load_command_table(self, args):
        from azext_containerapp.commands import load_command_table
        load_command_table(self, args)
        return self.command_table

    def load_arguments(self, command):
        from azext_containerapp._params import load_arguments
        load_arguments(self, command)


COMMAND_LOADER_CLS = ContainerappCommandsLoader
