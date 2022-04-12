# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import time
import unittest

from azure.cli.testsdk.scenario_tests import AllowLargeResponse
from azure.cli.testsdk import (ScenarioTest, ResourceGroupPreparer, JMESPathCheck)


TEST_DIR = os.path.abspath(os.path.join(os.path.abspath(__file__), '..'))


class ContainerappEnvScenarioTest(ScenarioTest):
    @AllowLargeResponse(8192)
    @ResourceGroupPreparer(location="centraluseuap")
    def test_containerapp_env_e2e(self, resource_group):
        env_name = self.create_random_name(prefix='containerapp-e2e-env', length=24)

        self.cmd('containerapp env create -g {} -n {}'.format(resource_group, env_name))

        # Sleep in case env create takes a while
        time.sleep(60)
        self.cmd('containerapp env list -g {}'.format(resource_group), checks=[
            JMESPathCheck('length(@)', 1),
            JMESPathCheck('[0].name', env_name),
        ])

        self.cmd('containerapp env show -n {} -g {}'.format(env_name, resource_group), checks=[
            JMESPathCheck('name', env_name),
        ])

        # Sleep in case containerapp create takes a while
        self.cmd('containerapp env delete -g {} -n {} --yes'.format(resource_group, env_name))

        # Sleep in case env delete takes a while
        time.sleep(60)
        self.cmd('containerapp env list -g {}'.format(resource_group), checks=[
            JMESPathCheck('length(@)', 0),
        ])
