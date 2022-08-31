# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import time


def create_containerapp_env(test_cls, env_name, resource_group):
    logs_workspace_name = test_cls.create_random_name(prefix='containerapp-env', length=24)
    logs_workspace_id = test_cls.cmd('monitor log-analytics workspace create -g {} -n {}'.format(resource_group, logs_workspace_name)).get_output_in_json()["customerId"]
    logs_workspace_key = test_cls.cmd('monitor log-analytics workspace get-shared-keys -g {} -n {}'.format(resource_group, logs_workspace_name)).get_output_in_json()["primarySharedKey"]

    test_cls.cmd('containerapp env create -g {} -n {} --logs-workspace-id {} --logs-workspace-key {}'.format(resource_group, env_name, logs_workspace_id, logs_workspace_key))

    containerapp_env = test_cls.cmd('containerapp env show -g {} -n {}'.format(resource_group, env_name)).get_output_in_json()

    while containerapp_env["properties"]["provisioningState"].lower() == "waiting":
        time.sleep(5)
        containerapp_env = test_cls.cmd('containerapp env show -g {} -n {}'.format(resource_group, env_name)).get_output_in_json()