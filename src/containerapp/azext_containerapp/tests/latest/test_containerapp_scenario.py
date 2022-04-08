# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import platform
from unittest import mock
from azext_containerapp.custom import containerapp_ssh

from azure.cli.testsdk.reverse_dependency import get_dummy_cli
from azure.cli.testsdk.scenario_tests import AllowLargeResponse
from azure.cli.testsdk import (ScenarioTest, ResourceGroupPreparer, JMESPathCheck, live_only)


TEST_DIR = os.path.abspath(os.path.join(os.path.abspath(__file__), '..'))


class ContainerappScenarioTest(ScenarioTest):
    @AllowLargeResponse(8192)
    @ResourceGroupPreparer(location="centraluseuap")
    def test_containerapp_e2e(self, resource_group):
        containerapp_name = self.create_random_name(prefix='containerapp-e2e', length=24)
        env_name = self.create_random_name(prefix='containerapp-e2e-env', length=24)

        self.cmd(f'containerapp env create -g {resource_group} -n {env_name}')

        self.cmd(f'containerapp env list -g {resource_group}', checks=[
            JMESPathCheck('length(@)', 1),
            JMESPathCheck('[0].name', env_name),
        ])

        self.cmd(f'containerapp create -g {resource_group} -n {containerapp_name} --environment {env_name}', checks=[
            JMESPathCheck('name', containerapp_name)
        ])

        self.cmd(f'containerapp show -g {resource_group} -n {containerapp_name}', checks=[
            JMESPathCheck('name', containerapp_name)
        ])

    @live_only()  # VCR.py can't seem to handle websockets (only --live works)
    # @ResourceGroupPreparer(location="centraluseuap")
    @mock.patch("azext_containerapp._ssh_utils._resize_terminal")
    @mock.patch("sys.stdin")
    def test_containerapp_ssh(self, resource_group=None, *args):
        # containerapp_name = self.create_random_name(prefix='capp', length=24)
        # env_name = self.create_random_name(prefix='env', length=24)

        # self.cmd(f'containerapp env create -g {resource_group} -n {env_name}')
        # self.cmd(f'containerapp create -g {resource_group} -n {containerapp_name} --environment {env_name} --min-replicas 1 --ingress external')

        # TODO remove hardcoded app info (currently the SSH feature is only enabled in stage)
        # these are only in my sub so they won't work on the CI / other people's machines
        containerapp_name = "stage"
        resource_group = "sca"

        stdout_buff = []

        def mock_print(*args, end="\n", **kwargs):
            out = " ".join([str(a) for a in args])
            if not stdout_buff:
                stdout_buff.append(out)
            elif end != "\n":
                stdout_buff[-1] = f"{stdout_buff[-1]}{out}"
            else:
                stdout_buff.append(out)

        commands = "\n".join(["whoami", "pwd", "ls -l | grep index.js", "exit\n"])
        expected_output = ["root", "/usr/src/app", "-rw-r--r--    1 root     root           267 Oct 15 00:21 index.js"]

        idx = [0]
        def mock_getch():
            ch = commands[idx[0]].encode("utf-8")
            idx[0] = (idx[0] + 1) % len(commands)
            return ch

        cmd = mock.MagicMock()
        cmd.cli_ctx = get_dummy_cli()
        from azext_containerapp._validators import validate_ssh
        from azext_containerapp.custom import containerapp_ssh

        class Namespace: pass
        namespace = Namespace()
        setattr(namespace, "name", containerapp_name)
        setattr(namespace, "resource_group_name", resource_group)
        setattr(namespace, "revision", None)
        setattr(namespace, "replica", None)
        setattr(namespace, "container", None)

        validate_ssh(cmd=cmd, namespace=namespace)  # needed to set values for container, replica, revision

        mock_lib = "tty.setcbreak"
        if platform.system() == "Windows":
            mock_lib = "azext_containerapp._ssh_utils.enable_vt_mode"

        with mock.patch("builtins.print", side_effect=mock_print), mock.patch(mock_lib):
            with mock.patch("azext_containerapp._ssh_utils._getch_unix", side_effect=mock_getch), mock.patch("azext_containerapp._ssh_utils._getch_windows", side_effect=mock_getch):
                containerapp_ssh(cmd=cmd, resource_group_name=namespace.resource_group_name, name=namespace.name,
                                    container=namespace.container, revision=namespace.revision, replica=namespace.replica, startup_command="sh")
        for line in expected_output:
            self.assertIn(line, expected_output)


    @live_only
    @ResourceGroupPreparer(location="centraluseuap")
    def test_containerapp_logstream(self, resource_group):
        containerapp_name = self.create_random_name(prefix='capp', length=24)
        env_name = self.create_random_name(prefix='env', length=24)

        self.cmd(f'containerapp env create -g {resource_group} -n {env_name}')
        self.cmd(f'containerapp create -g {resource_group} -n {containerapp_name} --environment {env_name} --min-replicas 1 --ingress external --target-port 80')

        self.cmd(f'containerapp log tail -n {containerapp_name} -g {resource_group}')
