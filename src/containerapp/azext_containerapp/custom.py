# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=line-too-long, consider-using-f-string, logging-format-interpolation, inconsistent-return-statements, broad-except, bare-except, too-many-statements, too-many-locals, too-many-boolean-expressions, too-many-branches, too-many-nested-blocks, pointless-statement, expression-not-assigned, unbalanced-tuple-unpacking

import threading
import sys
import time
from urllib.parse import urlparse
import requests

from azure.cli.core.azclierror import (
    RequiredArgumentMissingError,
    ValidationError,
    ResourceNotFoundError,
    CLIError,
    CLIInternalError,
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import open_page_in_browser, get_file_json
from azure.cli.command_modules.appservice._create_util import check_resource_group_exists
from azure.cli.command_modules.appservice._constants import GENERATE_RANDOM_APP_NAMES
from knack.log import get_logger

from msrestazure.tools import parse_resource_id, is_valid_resource_id
from msrest.exceptions import DeserializationError

from ._client_factory import handle_raw_exception
from ._clients import ManagedEnvironmentClient, ContainerAppClient, GitHubActionClient, DaprComponentClient
from ._github_oauth import get_github_access_token
from ._models import (
    ManagedEnvironment as ManagedEnvironmentModel,
    VnetConfiguration as VnetConfigurationModel,
    AppLogsConfiguration as AppLogsConfigurationModel,
    LogAnalyticsConfiguration as LogAnalyticsConfigurationModel,
    Ingress as IngressModel,
    Configuration as ConfigurationModel,
    Template as TemplateModel,
    RegistryCredentials as RegistryCredentialsModel,
    ContainerApp as ContainerAppModel,
    Dapr as DaprModel,
    ContainerResources as ContainerResourcesModel,
    Scale as ScaleModel,
    Container as ContainerModel,
    GitHubActionConfiguration,
    RegistryInfo as RegistryInfoModel,
    AzureCredentials as AzureCredentialsModel,
    SourceControl as SourceControlModel,
    ManagedServiceIdentity as ManagedServiceIdentityModel)
from ._utils import (_validate_subscription_registered, _get_location_from_resource_group, _ensure_location_allowed,
                     parse_secret_flags, store_as_secret_and_return_secret_ref, parse_env_var_flags,
                     _generate_log_analytics_if_not_provided, _get_existing_secrets, _convert_object_from_snake_to_camel_case,
                     _object_to_dict, _add_or_update_secrets, _remove_additional_attributes, _remove_readonly_attributes,
                     _add_or_update_env_vars, _add_or_update_tags, update_nested_dictionary, _update_traffic_weights,
                     _get_app_from_revision, raise_missing_token_suggestion, _infer_acr_credentials, _remove_registry_secret, _remove_secret,
                     _ensure_identity_resource_id, _remove_dapr_readonly_attributes, _registry_exists, _remove_env_vars,
                     _update_revision_env_secretrefs, get_randomized_name, _set_webapp_up_default_args, get_profile_username, create_resource_group,
                     get_resource_group, queue_acr_build, _get_acr_cred, create_new_acr, _get_log_analytics_workspace_name,
                     _get_default_containerapps_location, safe_get, is_int, create_service_principal_for_rbac,
                     get_container_app_if_exists, _get_name)

from ._ssh_utils import (SSH_DEFAULT_ENCODING, WebSocketConnection, read_ssh, get_stdin_writer, SSH_CTRL_C_MSG,
                         SSH_BACKUP_ENCODING, remove_token)

logger = get_logger(__name__)


# These properties should be under the "properties" attribute. Move the properties under "properties" attribute
def process_loaded_yaml(yaml_containerapp):
    if not yaml_containerapp.get('properties'):
        yaml_containerapp['properties'] = {}

    nested_properties = ["provisioningState", "managedEnvironmentId", "latestRevisionName", "latestRevisionFqdn",
                         "customDomainVerificationId", "configuration", "template", "outboundIPAddresses"]
    for nested_property in nested_properties:
        tmp = yaml_containerapp.get(nested_property)
        if tmp:
            yaml_containerapp['properties'][nested_property] = tmp
            del yaml_containerapp[nested_property]

    return yaml_containerapp


def load_yaml_file(file_name):
    import yaml
    import errno

    try:
        with open(file_name) as stream:  # pylint: disable=unspecified-encoding
            return yaml.safe_load(stream)
    except (IOError, OSError) as ex:
        if getattr(ex, 'errno', 0) == errno.ENOENT:
            raise ValidationError('{} does not exist'.format(file_name)) from ex
        raise
    except (yaml.parser.ParserError, UnicodeDecodeError) as ex:
        raise ValidationError('Error parsing {} ({})'.format(file_name, str(ex))) from ex


def create_deserializer():
    from ._sdk_models import ContainerApp  # pylint: disable=unused-import
    from msrest import Deserializer
    import inspect

    sdkClasses = inspect.getmembers(sys.modules["azext_containerapp._sdk_models"])
    deserializer = {}

    for sdkClass in sdkClasses:
        deserializer[sdkClass[0]] = sdkClass[1]

    return Deserializer(deserializer)


def update_containerapp_yaml(cmd, name, resource_group_name, file_name, from_revision=None, no_wait=False):
    yaml_containerapp = process_loaded_yaml(load_yaml_file(file_name))
    if type(yaml_containerapp) != dict:  # pylint: disable=unidiomatic-typecheck
        raise ValidationError('Invalid YAML provided. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.')

    if not yaml_containerapp.get('name'):
        yaml_containerapp['name'] = name
    elif yaml_containerapp.get('name').lower() != name.lower():
        logger.warning('The app name provided in the --yaml file "{}" does not match the one provided in the --name flag "{}". The one provided in the --yaml file will be used.'.format(
            yaml_containerapp.get('name'), name))
    name = yaml_containerapp.get('name')

    if not yaml_containerapp.get('type'):
        yaml_containerapp['type'] = 'Microsoft.App/containerApps'
    elif yaml_containerapp.get('type').lower() != "microsoft.app/containerapps":
        raise ValidationError('Containerapp type must be \"Microsoft.App/ContainerApps\"')

    current_containerapp_def = None
    containerapp_def = None
    try:
        current_containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except Exception:
        pass

    if not current_containerapp_def:
        raise ValidationError("The containerapp '{}' does not exist".format(name))

    # Change which revision we update from
    if from_revision:
        try:
            r = ContainerAppClient.show_revision(cmd=cmd, resource_group_name=resource_group_name, container_app_name=name, name=from_revision)
        except CLIError as e:
            handle_raw_exception(e)
        _update_revision_env_secretrefs(r["properties"]["template"]["containers"], name)
        current_containerapp_def["properties"]["template"] = r["properties"]["template"]

    # Deserialize the yaml into a ContainerApp object. Need this since we're not using SDK
    try:
        deserializer = create_deserializer()

        containerapp_def = deserializer('ContainerApp', yaml_containerapp)
    except DeserializationError as ex:
        raise ValidationError('Invalid YAML provided. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.') from ex

    # Remove tags before converting from snake case to camel case, then re-add tags. We don't want to change the case of the tags. Need this since we're not using SDK
    tags = None
    if yaml_containerapp.get('tags'):
        tags = yaml_containerapp.get('tags')
        del yaml_containerapp['tags']

    containerapp_def = _convert_object_from_snake_to_camel_case(_object_to_dict(containerapp_def))
    containerapp_def['tags'] = tags

    # After deserializing, some properties may need to be moved under the "properties" attribute. Need this since we're not using SDK
    containerapp_def = process_loaded_yaml(containerapp_def)

    _get_existing_secrets(cmd, resource_group_name, name, current_containerapp_def)

    update_nested_dictionary(current_containerapp_def, containerapp_def)

    # Remove "additionalProperties" and read-only attributes that are introduced in the deserialization. Need this since we're not using SDK
    _remove_additional_attributes(current_containerapp_def)
    _remove_readonly_attributes(current_containerapp_def)

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=current_containerapp_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            logger.warning('Containerapp creation in progress. Please monitor the creation using `az containerapp show -n {} -g {}`'.format(
                name, resource_group_name
            ))

        return r
    except Exception as e:
        handle_raw_exception(e)


def create_containerapp_yaml(cmd, name, resource_group_name, file_name, no_wait=False):
    yaml_containerapp = process_loaded_yaml(load_yaml_file(file_name))
    if type(yaml_containerapp) != dict:  # pylint: disable=unidiomatic-typecheck
        raise ValidationError('Invalid YAML provided. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.')

    if not yaml_containerapp.get('name'):
        yaml_containerapp['name'] = name
    elif yaml_containerapp.get('name').lower() != name.lower():
        logger.warning('The app name provided in the --yaml file "{}" does not match the one provided in the --name flag "{}". The one provided in the --yaml file will be used.'.format(
            yaml_containerapp.get('name'), name))
    name = yaml_containerapp.get('name')

    if not yaml_containerapp.get('type'):
        yaml_containerapp['type'] = 'Microsoft.App/containerApps'
    elif yaml_containerapp.get('type').lower() != "microsoft.app/containerapps":
        raise ValidationError('Containerapp type must be \"Microsoft.App/ContainerApps\"')

    # Deserialize the yaml into a ContainerApp object. Need this since we're not using SDK
    containerapp_def = None
    try:
        deserializer = create_deserializer()

        containerapp_def = deserializer('ContainerApp', yaml_containerapp)
    except DeserializationError as ex:
        raise ValidationError('Invalid YAML provided. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.') from ex

    # Remove tags before converting from snake case to camel case, then re-add tags. We don't want to change the case of the tags. Need this since we're not using SDK
    tags = None
    if yaml_containerapp.get('tags'):
        tags = yaml_containerapp.get('tags')
        del yaml_containerapp['tags']

    containerapp_def = _convert_object_from_snake_to_camel_case(_object_to_dict(containerapp_def))
    containerapp_def['tags'] = tags

    # After deserializing, some properties may need to be moved under the "properties" attribute. Need this since we're not using SDK
    containerapp_def = process_loaded_yaml(containerapp_def)

    # Remove "additionalProperties" and read-only attributes that are introduced in the deserialization. Need this since we're not using SDK
    _remove_additional_attributes(containerapp_def)
    _remove_readonly_attributes(containerapp_def)

    # Validate managed environment
    if not containerapp_def["properties"].get('managedEnvironmentId'):
        raise RequiredArgumentMissingError('managedEnvironmentId is required. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.')

    env_id = containerapp_def["properties"]['managedEnvironmentId']
    env_name = None
    env_rg = None
    env_info = None

    if is_valid_resource_id(env_id):
        parsed_managed_env = parse_resource_id(env_id)
        env_name = parsed_managed_env['name']
        env_rg = parsed_managed_env['resource_group']
    else:
        raise ValidationError('Invalid managedEnvironmentId specified. Environment not found')

    try:
        env_info = ManagedEnvironmentClient.show(cmd=cmd, resource_group_name=env_rg, name=env_name)
    except:
        pass

    if not env_info:
        raise ValidationError("The environment '{}' in resource group '{}' was not found".format(env_name, env_rg))

    # Validate location
    if not containerapp_def.get('location'):
        containerapp_def['location'] = env_info['location']

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            logger.warning('Containerapp creation in progress. Please monitor the creation using `az containerapp show -n {} -g {}`'.format(
                name, resource_group_name
            ))

        if "configuration" in r["properties"] and "ingress" in r["properties"]["configuration"] and "fqdn" in r["properties"]["configuration"]["ingress"]:
            logger.warning("\nContainer app created. Access your app at https://{}/\n".format(r["properties"]["configuration"]["ingress"]["fqdn"]))
        else:
            logger.warning("\nContainer app created. To access it over HTTPS, enable ingress: az containerapp ingress enable --help\n")

        return r
    except Exception as e:
        handle_raw_exception(e)


def create_containerapp(cmd,
                        name,
                        resource_group_name,
                        yaml=None,
                        image=None,
                        container_name=None,
                        managed_env=None,
                        min_replicas=None,
                        max_replicas=None,
                        target_port=None,
                        transport="auto",
                        ingress=None,
                        revisions_mode="single",
                        secrets=None,
                        env_vars=None,
                        cpu=None,
                        memory=None,
                        registry_server=None,
                        registry_user=None,
                        registry_pass=None,
                        dapr_enabled=False,
                        dapr_app_port=None,
                        dapr_app_id=None,
                        dapr_app_protocol=None,
                        revision_suffix=None,
                        startup_command=None,
                        args=None,
                        tags=None,
                        no_wait=False,
                        system_assigned=False,
                        disable_warnings=False,
                        user_assigned=None):
    _validate_subscription_registered(cmd, "Microsoft.App")

    if yaml:
        if image or managed_env or min_replicas or max_replicas or target_port or ingress or\
            revisions_mode or secrets or env_vars or cpu or memory or registry_server or\
            registry_user or registry_pass or dapr_enabled or dapr_app_port or dapr_app_id or\
                startup_command or args or tags:
            not disable_warnings and logger.warning('Additional flags were passed along with --yaml. These flags will be ignored, and the configuration defined in the yaml will be used instead')
        return create_containerapp_yaml(cmd=cmd, name=name, resource_group_name=resource_group_name, file_name=yaml, no_wait=no_wait)

    if not image:
        image = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"

    if managed_env is None:
        raise RequiredArgumentMissingError('Usage error: --environment is required if not using --yaml')

    # Validate managed environment
    parsed_managed_env = parse_resource_id(managed_env)
    managed_env_name = parsed_managed_env['name']
    managed_env_rg = parsed_managed_env['resource_group']
    managed_env_info = None

    try:
        managed_env_info = ManagedEnvironmentClient.show(cmd=cmd, resource_group_name=managed_env_rg, name=managed_env_name)
    except:
        pass

    if not managed_env_info:
        raise ValidationError("The environment '{}' does not exist. Specify a valid environment".format(managed_env))

    location = managed_env_info["location"]
    _ensure_location_allowed(cmd, location, "Microsoft.App", "containerApps")

    external_ingress = None
    if ingress is not None:
        if ingress.lower() == "internal":
            external_ingress = False
        elif ingress.lower() == "external":
            external_ingress = True

    ingress_def = None
    if target_port is not None and ingress is not None:
        ingress_def = IngressModel
        ingress_def["external"] = external_ingress
        ingress_def["targetPort"] = target_port
        ingress_def["transport"] = transport

    secrets_def = None
    if secrets is not None:
        secrets_def = parse_secret_flags(secrets)

    registries_def = None
    if registry_server is not None:
        registries_def = RegistryCredentialsModel

        # Infer credentials if not supplied and its azurecr
        if registry_user is None or registry_pass is None:
            registry_user, registry_pass = _infer_acr_credentials(cmd, registry_server, disable_warnings)

        registries_def["server"] = registry_server
        registries_def["username"] = registry_user

        if secrets_def is None:
            secrets_def = []
        registries_def["passwordSecretRef"] = store_as_secret_and_return_secret_ref(secrets_def, registry_user, registry_server, registry_pass, disable_warnings=disable_warnings)

    dapr_def = None
    if dapr_enabled:
        dapr_def = DaprModel
        dapr_def["enabled"] = True
        dapr_def["appId"] = dapr_app_id
        dapr_def["appPort"] = dapr_app_port
        dapr_def["appProtocol"] = dapr_app_protocol

    config_def = ConfigurationModel
    config_def["secrets"] = secrets_def
    config_def["activeRevisionsMode"] = revisions_mode
    config_def["ingress"] = ingress_def
    config_def["registries"] = [registries_def] if registries_def is not None else None
    config_def["dapr"] = dapr_def

    # Identity actions
    identity_def = ManagedServiceIdentityModel
    identity_def["type"] = "None"

    assign_system_identity = system_assigned
    if user_assigned:
        assign_user_identities = [x.lower() for x in user_assigned]
    else:
        assign_user_identities = []

    if assign_system_identity and assign_user_identities:
        identity_def["type"] = "SystemAssigned, UserAssigned"
    elif assign_system_identity:
        identity_def["type"] = "SystemAssigned"
    elif assign_user_identities:
        identity_def["type"] = "UserAssigned"

    if assign_user_identities:
        identity_def["userAssignedIdentities"] = {}
        subscription_id = get_subscription_id(cmd.cli_ctx)

        for r in assign_user_identities:
            r = _ensure_identity_resource_id(subscription_id, resource_group_name, r)
            identity_def["userAssignedIdentities"][r] = {}  # pylint: disable=unsupported-assignment-operation

    scale_def = None
    if min_replicas is not None or max_replicas is not None:
        scale_def = ScaleModel
        scale_def["minReplicas"] = min_replicas
        scale_def["maxReplicas"] = max_replicas

    resources_def = None
    if cpu is not None or memory is not None:
        resources_def = ContainerResourcesModel
        resources_def["cpu"] = cpu
        resources_def["memory"] = memory

    container_def = ContainerModel
    container_def["name"] = container_name if container_name else name
    container_def["image"] = image
    if env_vars is not None:
        container_def["env"] = parse_env_var_flags(env_vars)
    if startup_command is not None:
        container_def["command"] = startup_command
    if args is not None:
        container_def["args"] = args
    if resources_def is not None:
        container_def["resources"] = resources_def

    template_def = TemplateModel
    template_def["containers"] = [container_def]
    template_def["scale"] = scale_def

    if revision_suffix is not None:
        template_def["revisionSuffix"] = revision_suffix

    containerapp_def = ContainerAppModel
    containerapp_def["location"] = location
    containerapp_def["identity"] = identity_def
    containerapp_def["properties"]["managedEnvironmentId"] = managed_env
    containerapp_def["properties"]["configuration"] = config_def
    containerapp_def["properties"]["template"] = template_def
    containerapp_def["tags"] = tags

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            not disable_warnings and logger.warning('Containerapp creation in progress. Please monitor the creation using `az containerapp show -n {} -g {}`'.format(name, resource_group_name))

        if "configuration" in r["properties"] and "ingress" in r["properties"]["configuration"] and "fqdn" in r["properties"]["configuration"]["ingress"]:
            not disable_warnings and logger.warning("\nContainer app created. Access your app at https://{}/\n".format(r["properties"]["configuration"]["ingress"]["fqdn"]))
        else:
            not disable_warnings and logger.warning("\nContainer app created. To access it over HTTPS, enable ingress: az containerapp ingress enable --help\n")

        return r
    except Exception as e:
        handle_raw_exception(e)


def update_containerapp_logic(cmd,
                              name,
                              resource_group_name,
                              yaml=None,
                              image=None,
                              container_name=None,
                              min_replicas=None,
                              max_replicas=None,
                              set_env_vars=None,
                              remove_env_vars=None,
                              replace_env_vars=None,
                              remove_all_env_vars=False,
                              cpu=None,
                              memory=None,
                              revision_suffix=None,
                              startup_command=None,
                              args=None,
                              tags=None,
                              no_wait=False,
                              from_revision=None):
    _validate_subscription_registered(cmd, "Microsoft.App")

    if yaml:
        if image or min_replicas or max_replicas or\
           set_env_vars or remove_env_vars or replace_env_vars or remove_all_env_vars or cpu or memory or\
           startup_command or args or tags:
            logger.warning('Additional flags were passed along with --yaml. These flags will be ignored, and the configuration defined in the yaml will be used instead')
        return update_containerapp_yaml(cmd=cmd, name=name, resource_group_name=resource_group_name, file_name=yaml, no_wait=no_wait, from_revision=from_revision)

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    if from_revision:
        try:
            r = ContainerAppClient.show_revision(cmd=cmd, resource_group_name=resource_group_name, container_app_name=name, name=from_revision)
        except CLIError as e:
            # Error handle the case where revision not found?
            handle_raw_exception(e)

        _update_revision_env_secretrefs(r["properties"]["template"]["containers"], name)
        containerapp_def["properties"]["template"] = r["properties"]["template"]

    # Doing this while API has bug. If env var is an empty string, API doesn't return "value" even though the "value" should be an empty string
    if "properties" in containerapp_def and "template" in containerapp_def["properties"] and "containers" in containerapp_def["properties"]["template"]:
        for container in containerapp_def["properties"]["template"]["containers"]:
            if "env" in container:
                for e in container["env"]:
                    if "value" not in e:
                        e["value"] = ""

    update_map = {}
    update_map['scale'] = min_replicas or max_replicas
    update_map['container'] = image or container_name or set_env_vars is not None or remove_env_vars is not None or replace_env_vars is not None or remove_all_env_vars or cpu or memory or startup_command is not None or args is not None

    if tags:
        _add_or_update_tags(containerapp_def, tags)

    if revision_suffix is not None:
        containerapp_def["properties"]["template"]["revisionSuffix"] = revision_suffix

    # Containers
    if update_map["container"]:
        if not container_name:
            if len(containerapp_def["properties"]["template"]["containers"]) == 1:
                container_name = containerapp_def["properties"]["template"]["containers"][0]["name"]
            else:
                raise ValidationError("Usage error: --container-name is required when adding or updating a container")

        # Check if updating existing container
        updating_existing_container = False
        for c in containerapp_def["properties"]["template"]["containers"]:
            if c["name"].lower() == container_name.lower():
                updating_existing_container = True

                if image is not None:
                    c["image"] = image

                if set_env_vars is not None:
                    if "env" not in c or not c["env"]:
                        c["env"] = []
                    # env vars
                    _add_or_update_env_vars(c["env"], parse_env_var_flags(set_env_vars), is_add=True)

                if replace_env_vars is not None:
                    if "env" not in c or not c["env"]:
                        c["env"] = []
                    # env vars
                    _add_or_update_env_vars(c["env"], parse_env_var_flags(replace_env_vars))

                if remove_env_vars is not None:
                    if "env" not in c or not c["env"]:
                        c["env"] = []
                    # env vars
                    _remove_env_vars(c["env"], remove_env_vars)

                if remove_all_env_vars:
                    c["env"] = []

                if startup_command is not None:
                    if isinstance(startup_command, list) and not startup_command:
                        c["command"] = None
                    else:
                        c["command"] = startup_command
                if args is not None:
                    if isinstance(args, list) and not args:
                        c["args"] = None
                    else:
                        c["args"] = args
                if cpu is not None or memory is not None:
                    if "resources" in c and c["resources"]:
                        if cpu is not None:
                            c["resources"]["cpu"] = cpu
                        if memory is not None:
                            c["resources"]["memory"] = memory
                    else:
                        c["resources"] = {
                            "cpu": cpu,
                            "memory": memory
                        }

        # If not updating existing container, add as new container
        if not updating_existing_container:
            if image is None:
                raise ValidationError("Usage error: --image is required when adding a new container")

            resources_def = None
            if cpu is not None or memory is not None:
                resources_def = ContainerResourcesModel
                resources_def["cpu"] = cpu
                resources_def["memory"] = memory

            container_def = ContainerModel
            container_def["name"] = container_name
            container_def["image"] = image
            container_def["env"] = []

            if set_env_vars is not None:
                # env vars
                _add_or_update_env_vars(container_def["env"], parse_env_var_flags(set_env_vars), is_add=True)

            if replace_env_vars is not None:
                # env vars
                _add_or_update_env_vars(container_def["env"], parse_env_var_flags(replace_env_vars))

            if remove_env_vars is not None:
                # env vars
                _remove_env_vars(container_def["env"], remove_env_vars)

            if remove_all_env_vars:
                container_def["env"] = []

            if startup_command is not None:
                if isinstance(startup_command, list) and not startup_command:
                    container_def["command"] = None
                else:
                    container_def["command"] = startup_command
            if args is not None:
                if isinstance(args, list) and not args:
                    container_def["args"] = None
                else:
                    container_def["args"] = args
            if resources_def is not None:
                container_def["resources"] = resources_def

            containerapp_def["properties"]["template"]["containers"].append(container_def)

    # Scale
    if update_map["scale"]:
        if "scale" not in containerapp_def["properties"]["template"]:
            containerapp_def["properties"]["template"]["scale"] = {}
        if min_replicas is not None:
            containerapp_def["properties"]["template"]["scale"]["minReplicas"] = min_replicas
        if max_replicas is not None:
            containerapp_def["properties"]["template"]["scale"]["maxReplicas"] = max_replicas

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            logger.warning('Containerapp update in progress. Please monitor the update using `az containerapp show -n {} -g {}`'.format(name, resource_group_name))

        return r
    except Exception as e:
        handle_raw_exception(e)


def update_containerapp(cmd,
                        name,
                        resource_group_name,
                        yaml=None,
                        image=None,
                        container_name=None,
                        min_replicas=None,
                        max_replicas=None,
                        set_env_vars=None,
                        remove_env_vars=None,
                        replace_env_vars=None,
                        remove_all_env_vars=False,
                        cpu=None,
                        memory=None,
                        revision_suffix=None,
                        startup_command=None,
                        args=None,
                        tags=None,
                        no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    return update_containerapp_logic(cmd,
                                     name,
                                     resource_group_name,
                                     yaml,
                                     image,
                                     container_name,
                                     min_replicas,
                                     max_replicas,
                                     set_env_vars,
                                     remove_env_vars,
                                     replace_env_vars,
                                     remove_all_env_vars,
                                     cpu,
                                     memory,
                                     revision_suffix,
                                     startup_command,
                                     args,
                                     tags,
                                     no_wait)


def show_containerapp(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        return ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)


def list_containerapp(cmd, resource_group_name=None):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        containerapps = []
        if resource_group_name is None:
            containerapps = ContainerAppClient.list_by_subscription(cmd=cmd)
        else:
            containerapps = ContainerAppClient.list_by_resource_group(cmd=cmd, resource_group_name=resource_group_name)

        return containerapps
    except CLIError as e:
        handle_raw_exception(e)


def delete_containerapp(cmd, name, resource_group_name, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        return ContainerAppClient.delete(cmd=cmd, name=name, resource_group_name=resource_group_name, no_wait=no_wait)
    except CLIError as e:
        handle_raw_exception(e)


def create_managed_environment(cmd,
                               name,
                               resource_group_name,
                               logs_customer_id=None,
                               logs_key=None,
                               location=None,
                               instrumentation_key=None,
                               infrastructure_subnet_resource_id=None,
                               docker_bridge_cidr=None,
                               platform_reserved_cidr=None,
                               platform_reserved_dns_ip=None,
                               internal_only=False,
                               tags=None,
                               disable_warnings=False,
                               no_wait=False):

    location = location or _get_location_from_resource_group(cmd.cli_ctx, resource_group_name)

    _validate_subscription_registered(cmd, "Microsoft.App")
    _ensure_location_allowed(cmd, location, "Microsoft.App", "managedEnvironments")

    if logs_customer_id is None or logs_key is None:
        logs_customer_id, logs_key = _generate_log_analytics_if_not_provided(cmd, logs_customer_id, logs_key, location, resource_group_name)

    log_analytics_config_def = LogAnalyticsConfigurationModel
    log_analytics_config_def["customerId"] = logs_customer_id
    log_analytics_config_def["sharedKey"] = logs_key

    app_logs_config_def = AppLogsConfigurationModel
    app_logs_config_def["destination"] = "log-analytics"
    app_logs_config_def["logAnalyticsConfiguration"] = log_analytics_config_def

    managed_env_def = ManagedEnvironmentModel
    managed_env_def["location"] = location
    managed_env_def["properties"]["internalLoadBalancerEnabled"] = False
    managed_env_def["properties"]["appLogsConfiguration"] = app_logs_config_def
    managed_env_def["tags"] = tags

    if instrumentation_key is not None:
        managed_env_def["properties"]["daprAIInstrumentationKey"] = instrumentation_key

    if infrastructure_subnet_resource_id or docker_bridge_cidr or platform_reserved_cidr or platform_reserved_dns_ip:
        vnet_config_def = VnetConfigurationModel

        if infrastructure_subnet_resource_id is not None:
            vnet_config_def["infrastructureSubnetId"] = infrastructure_subnet_resource_id

        if docker_bridge_cidr is not None:
            vnet_config_def["dockerBridgeCidr"] = docker_bridge_cidr

        if platform_reserved_cidr is not None:
            vnet_config_def["platformReservedCidr"] = platform_reserved_cidr

        if platform_reserved_dns_ip is not None:
            vnet_config_def["platformReservedDnsIP"] = platform_reserved_dns_ip

        managed_env_def["properties"]["vnetConfiguration"] = vnet_config_def

    if internal_only:
        if not infrastructure_subnet_resource_id:
            raise ValidationError('Infrastructure subnet resource ID needs to be supplied for internal only environments.')
        managed_env_def["properties"]["internalLoadBalancerEnabled"] = True

    try:
        r = ManagedEnvironmentClient.create(
            cmd=cmd, resource_group_name=resource_group_name, name=name, managed_environment_envelope=managed_env_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            not disable_warnings and logger.warning('Containerapp environment creation in progress. Please monitor the creation using `az containerapp env show -n {} -g {}`'.format(name, resource_group_name))

        not disable_warnings and logger.warning("\nContainer Apps environment created. To deploy a container app, use: az containerapp create --help\n")

        return r
    except Exception as e:
        handle_raw_exception(e)


def update_managed_environment(cmd,
                               name,
                               resource_group_name,
                               tags=None,
                               no_wait=False):
    raise CLIInternalError('Containerapp env update is not yet supported.')


def show_managed_environment(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        return ManagedEnvironmentClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)


def list_managed_environments(cmd, resource_group_name=None):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        managed_envs = []
        if resource_group_name is None:
            managed_envs = ManagedEnvironmentClient.list_by_subscription(cmd=cmd)
        else:
            managed_envs = ManagedEnvironmentClient.list_by_resource_group(cmd=cmd, resource_group_name=resource_group_name)

        return managed_envs
    except CLIError as e:
        handle_raw_exception(e)


def delete_managed_environment(cmd, name, resource_group_name, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        return ManagedEnvironmentClient.delete(cmd=cmd, name=name, resource_group_name=resource_group_name, no_wait=no_wait)
    except CLIError as e:
        handle_raw_exception(e)


def assign_managed_identity(cmd, name, resource_group_name, system_assigned=False, user_assigned=None, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    assign_system_identity = system_assigned
    if not user_assigned:
        user_assigned = []
    assign_user_identities = [x.lower() for x in user_assigned]

    containerapp_def = None

    # Get containerapp properties of CA we are updating
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    # If identity not returned
    try:
        containerapp_def["identity"]
        containerapp_def["identity"]["type"]
    except:
        containerapp_def["identity"] = {}
        containerapp_def["identity"]["type"] = "None"

    if assign_system_identity and containerapp_def["identity"]["type"].__contains__("SystemAssigned"):
        logger.warning("System identity is already assigned to containerapp")

    # Assign correct type
    try:
        if containerapp_def["identity"]["type"] != "None":
            if containerapp_def["identity"]["type"] == "SystemAssigned" and assign_user_identities:
                containerapp_def["identity"]["type"] = "SystemAssigned,UserAssigned"
            if containerapp_def["identity"]["type"] == "UserAssigned" and assign_system_identity:
                containerapp_def["identity"]["type"] = "SystemAssigned,UserAssigned"
        else:
            if assign_system_identity and assign_user_identities:
                containerapp_def["identity"]["type"] = "SystemAssigned,UserAssigned"
            elif assign_system_identity:
                containerapp_def["identity"]["type"] = "SystemAssigned"
            elif assign_user_identities:
                containerapp_def["identity"]["type"] = "UserAssigned"
    except:
        # Always returns "type": "None" when CA has no previous identities
        pass

    if assign_user_identities:
        try:
            containerapp_def["identity"]["userAssignedIdentities"]
        except:
            containerapp_def["identity"]["userAssignedIdentities"] = {}

        subscription_id = get_subscription_id(cmd.cli_ctx)

        for r in assign_user_identities:
            r = _ensure_identity_resource_id(subscription_id, resource_group_name, r).replace("resourceGroup", "resourcegroup")
            isExisting = False

            for old_user_identity in containerapp_def["identity"]["userAssignedIdentities"]:
                if old_user_identity.lower() == r.lower():
                    isExisting = True
                    logger.warning("User identity {} is already assigned to containerapp".format(old_user_identity))
                    break

            if not isExisting:
                containerapp_def["identity"]["userAssignedIdentities"][r] = {}

    try:
        r = ContainerAppClient.create_or_update(cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        # If identity is not returned, do nothing
        return r["identity"]

    except Exception as e:
        handle_raw_exception(e)


def remove_managed_identity(cmd, name, resource_group_name, system_assigned=False, user_assigned=None, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    remove_system_identity = system_assigned
    remove_user_identities = user_assigned

    if user_assigned:
        remove_id_size = len(remove_user_identities)

        # Remove duplicate identities that are passed and notify
        remove_user_identities = list(set(remove_user_identities))
        if remove_id_size != len(remove_user_identities):
            logger.warning("At least one identity was passed twice.")

    containerapp_def = None
    # Get containerapp properties of CA we are updating
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    # If identity not returned
    try:
        containerapp_def["identity"]
        containerapp_def["identity"]["type"]
    except:
        containerapp_def["identity"] = {}
        containerapp_def["identity"]["type"] = "None"

    if containerapp_def["identity"]["type"] == "None":
        raise InvalidArgumentValueError("The containerapp {} has no system or user assigned identities.".format(name))

    if remove_system_identity:
        if containerapp_def["identity"]["type"] == "UserAssigned":
            raise InvalidArgumentValueError("The containerapp {} has no system assigned identities.".format(name))
        containerapp_def["identity"]["type"] = ("None" if containerapp_def["identity"]["type"] == "SystemAssigned" else "UserAssigned")

    if isinstance(user_assigned, list) and not user_assigned:
        containerapp_def["identity"]["userAssignedIdentities"] = {}
        remove_user_identities = []

        if containerapp_def["identity"]["userAssignedIdentities"] == {}:
            containerapp_def["identity"]["userAssignedIdentities"] = None
            containerapp_def["identity"]["type"] = ("None" if containerapp_def["identity"]["type"] == "UserAssigned" else "SystemAssigned")

    if remove_user_identities:
        subscription_id = get_subscription_id(cmd.cli_ctx)
        try:
            containerapp_def["identity"]["userAssignedIdentities"]
        except:
            containerapp_def["identity"]["userAssignedIdentities"] = {}
        for remove_id in remove_user_identities:
            given_id = remove_id
            remove_id = _ensure_identity_resource_id(subscription_id, resource_group_name, remove_id)
            wasRemoved = False

            for old_user_identity in containerapp_def["identity"]["userAssignedIdentities"]:
                if old_user_identity.lower() == remove_id.lower():
                    containerapp_def["identity"]["userAssignedIdentities"].pop(old_user_identity)
                    wasRemoved = True
                    break

            if not wasRemoved:
                raise InvalidArgumentValueError("The containerapp does not have specified user identity '{}' assigned, so it cannot be removed.".format(given_id))

        if containerapp_def["identity"]["userAssignedIdentities"] == {}:
            containerapp_def["identity"]["userAssignedIdentities"] = None
            containerapp_def["identity"]["type"] = ("None" if containerapp_def["identity"]["type"] == "UserAssigned" else "SystemAssigned")

    try:
        r = ContainerAppClient.create_or_update(cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        return r["identity"]
    except Exception as e:
        handle_raw_exception(e)


def show_managed_identity(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        r = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)

    try:
        return r["identity"]
    except:
        r["identity"] = {}
        r["identity"]["type"] = "None"
        return r["identity"]


def _validate_github(repo, branch, token):
    from github import Github, GithubException
    from github.GithubException import BadCredentialsException

    if repo:
        g = Github(token)
        github_repo = None
        try:
            github_repo = g.get_repo(repo)
            if not github_repo.permissions.push or not github_repo.permissions.maintain:
                raise ValidationError("The token does not have appropriate access rights to repository {}.".format(repo))
            try:
                github_repo.get_branch(branch=branch)
            except GithubException as e:
                error_msg = "Encountered GitHub error when accessing {} branch in {} repo.".format(branch, repo)
                if e.data and e.data['message']:
                    error_msg += " Error: {}".format(e.data['message'])
                raise CLIInternalError(error_msg) from e
            logger.warning('Verified GitHub repo and branch')
        except BadCredentialsException as e:
            raise ValidationError("Could not authenticate to the repository. Please create a Personal Access Token and use "
                                    "the --token argument. Run 'az webapp deployment github-actions add --help' "
                                    "for more information.") from e
        except GithubException as e:
            error_msg = "Encountered GitHub error when accessing {} repo".format(repo)
            if e.data and e.data['message']:
                error_msg += " Error: {}".format(e.data['message'])
            raise CLIInternalError(error_msg) from e


def _await_github_action(cmd, token, repo, branch, name, resource_group_name, timeout=300):
    from github import Github
    from time import sleep
    from ._clients import PollingAnimation
    from datetime import datetime

    start = datetime.utcnow()

    animation = PollingAnimation()
    animation.tick()
    g = Github(token)

    github_repo = g.get_repo(repo)


    workflow = None
    while workflow is None:
        workflows = github_repo.get_workflows()
        animation.flush()
        for wf in workflows:
            if wf.path.startswith(f".github/workflows/{name}") and "Trigger auto deployment for containerapp" in wf.name:
                workflow = wf
                break

        gh_action_status = safe_get(show_github_action(cmd, name, resource_group_name), "properties", "operationState")
        if gh_action_status == "Failed":
            raise CLIInternalError("The Github Action creation failed.")
        sleep(1)
        animation.tick()

        if (datetime.utcnow() - start).seconds >= timeout:
            raise CLIInternalError("Timed out while waiting for the Github action to start.")

    animation.flush()
    animation.tick(); animation.flush()
    run = workflow.get_runs()[0]
    logger.warning(f"Github action run: https://github.com/{repo}/actions/runs/{run.id}")
    logger.warning("Waiting for deployment to complete...")
    run_id = run.id
    status = run.status
    while status == "queued" or status == "in_progress":
        sleep(3)
        animation.tick()
        status = [wf.status for wf in workflow.get_runs() if wf.id == run_id][0]
        animation.flush()
        if (datetime.utcnow() - start).seconds >= timeout:
            raise CLIInternalError("Timed out while waiting for the Github action to start.")

    if status != "completed":
        raise ValidationError(f"Github action deployment ended with status: {status}")


def _repo_url_to_name(repo_url):
    repo = None
    repo = repo_url.split('/')
    if len(repo) >= 2:
        repo = '/'.join(repo[-2:])
    return repo


def create_or_update_github_action(cmd,
                                   name,
                                   resource_group_name,
                                   repo_url,
                                   registry_url=None,
                                   registry_username=None,
                                   registry_password=None,
                                   branch=None,
                                   token=None,
                                   login_with_github=False,
                                   image=None,
                                   context_path=None,
                                   service_principal_client_id=None,
                                   service_principal_client_secret=None,
                                   service_principal_tenant_id=None,
                                   no_wait=False):
    if not token and not login_with_github:
        raise_missing_token_suggestion()
    elif not token:
        scopes = ["admin:repo_hook", "repo", "workflow"]
        token = get_github_access_token(cmd, scopes)
    elif token and login_with_github:
        logger.warning("Both token and --login-with-github flag are provided. Will use provided token")

    repo = _repo_url_to_name(repo_url)
    repo_url = f"https://github.com/{repo}"  # allow specifying repo as <user>/<repo> without the full github url

    _validate_github(repo, branch, token)

    source_control_info = None

    try:
        source_control_info = GitHubActionClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)

    except Exception as ex:
        if not service_principal_client_id or not service_principal_client_secret or not service_principal_tenant_id:
            raise RequiredArgumentMissingError('Service principal client ID, secret and tenant ID are required to add github actions for the first time. Please create one using the command \"az ad sp create-for-rbac --name {{name}} --role contributor --scopes /subscriptions/{{subscription}}/resourceGroups/{{resourceGroup}} --sdk-auth\"') from ex
        source_control_info = SourceControlModel

    source_control_info["properties"]["repoUrl"] = repo_url

    if branch:
        source_control_info["properties"]["branch"] = branch
    if not source_control_info["properties"]["branch"]:
        source_control_info["properties"]["branch"] = "main"

    azure_credentials = None

    if service_principal_client_id or service_principal_client_secret or service_principal_tenant_id:
        azure_credentials = AzureCredentialsModel
        azure_credentials["clientId"] = service_principal_client_id
        azure_credentials["clientSecret"] = service_principal_client_secret
        azure_credentials["tenantId"] = service_principal_tenant_id
        azure_credentials["subscriptionId"] = get_subscription_id(cmd.cli_ctx)

    # Registry
    if registry_username is None or registry_password is None:
        # If registry is Azure Container Registry, we can try inferring credentials
        if not registry_url or '.azurecr.io' not in registry_url:
            raise RequiredArgumentMissingError('Registry url is required if using Azure Container Registry, otherwise Registry username and password are required if using Dockerhub')
        logger.warning('No credential was provided to access Azure Container Registry. Trying to look up...')
        parsed = urlparse(registry_url)
        registry_name = (parsed.netloc if parsed.scheme else parsed.path).split('.')[0]

        try:
            registry_username, registry_password = _get_acr_cred(cmd.cli_ctx, registry_name)
        except Exception as ex:
            raise RequiredArgumentMissingError('Failed to retrieve credentials for container registry. Please provide the registry username and password') from ex

    registry_info = RegistryInfoModel
    registry_info["registryUrl"] = registry_url
    registry_info["registryUserName"] = registry_username
    registry_info["registryPassword"] = registry_password

    github_action_configuration = GitHubActionConfiguration
    github_action_configuration["registryInfo"] = registry_info
    github_action_configuration["azureCredentials"] = azure_credentials
    github_action_configuration["contextPath"] = context_path
    github_action_configuration["image"] = image

    source_control_info["properties"]["githubActionConfiguration"] = github_action_configuration

    headers = ["x-ms-github-auxiliary={}".format(token)]

    try:
        logger.warning("Creating Github action...")
        r = GitHubActionClient.create_or_update(cmd=cmd, resource_group_name=resource_group_name, name=name, github_action_envelope=source_control_info, headers=headers, no_wait=no_wait)
        if not no_wait:
            _await_github_action(cmd, token, repo, branch, name, resource_group_name)
        return r
    except Exception as e:
        handle_raw_exception(e)


def show_github_action(cmd, name, resource_group_name):
    try:
        return GitHubActionClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except Exception as e:
        handle_raw_exception(e)


def delete_github_action(cmd, name, resource_group_name, token=None, login_with_github=False):
    # Check if there is an existing source control to delete
    try:
        github_action_config = GitHubActionClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except Exception as e:
        handle_raw_exception(e)

    repo_url = github_action_config["properties"]["repoUrl"]

    if not token and not login_with_github:
        raise_missing_token_suggestion()
    elif not token:
        scopes = ["admin:repo_hook", "repo", "workflow"]
        token = get_github_access_token(cmd, scopes)
    elif token and login_with_github:
        logger.warning("Both token and --login-with-github flag are provided. Will use provided token")

    # Check if PAT can access repo
    try:
        # Verify github repo
        from github import Github, GithubException
        from github.GithubException import BadCredentialsException

        repo = None
        repo = repo_url.split('/')
        if len(repo) >= 2:
            repo = '/'.join(repo[-2:])

        if repo:
            g = Github(token)
            github_repo = None
            try:
                github_repo = g.get_repo(repo)
                if not github_repo.permissions.push or not github_repo.permissions.maintain:
                    raise ValidationError("The token does not have appropriate access rights to repository {}.".format(repo))
            except BadCredentialsException as e:
                raise CLIInternalError("Could not authenticate to the repository. Please create a Personal Access Token and use "
                                       "the --token argument. Run 'az webapp deployment github-actions add --help' "
                                       "for more information.") from e
            except GithubException as e:
                error_msg = "Encountered GitHub error when accessing {} repo".format(repo)
                if e.data and e.data['message']:
                    error_msg += " Error: {}".format(e.data['message'])
                raise CLIInternalError(error_msg) from e
    except CLIError as clierror:
        raise clierror
    except Exception:
        # If exception due to github package missing, etc just continue without validating the repo and rely on api validation
        pass

    headers = ["x-ms-github-auxiliary={}".format(token)]

    try:
        return GitHubActionClient.delete(cmd=cmd, resource_group_name=resource_group_name, name=name, headers=headers)
    except Exception as e:
        handle_raw_exception(e)


def list_revisions(cmd, name, resource_group_name):
    try:
        return ContainerAppClient.list_revisions(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)


def show_revision(cmd, resource_group_name, revision_name, name=None):
    if not name:
        name = _get_app_from_revision(revision_name)

    try:
        return ContainerAppClient.show_revision(cmd=cmd, resource_group_name=resource_group_name, container_app_name=name, name=revision_name)
    except CLIError as e:
        handle_raw_exception(e)


def restart_revision(cmd, resource_group_name, revision_name, name=None):
    if not name:
        name = _get_app_from_revision(revision_name)

    try:
        return ContainerAppClient.restart_revision(cmd=cmd, resource_group_name=resource_group_name, container_app_name=name, name=revision_name)
    except CLIError as e:
        handle_raw_exception(e)


def activate_revision(cmd, resource_group_name, revision_name, name=None):
    if not name:
        name = _get_app_from_revision(revision_name)

    try:
        return ContainerAppClient.activate_revision(cmd=cmd, resource_group_name=resource_group_name, container_app_name=name, name=revision_name)
    except CLIError as e:
        handle_raw_exception(e)


def deactivate_revision(cmd, resource_group_name, revision_name, name=None):
    if not name:
        name = _get_app_from_revision(revision_name)

    try:
        return ContainerAppClient.deactivate_revision(cmd=cmd, resource_group_name=resource_group_name, container_app_name=name, name=revision_name)
    except CLIError as e:
        handle_raw_exception(e)


def copy_revision(cmd,
                  resource_group_name,
                  from_revision=None,
                  # label=None,
                  name=None,
                  yaml=None,
                  image=None,
                  container_name=None,
                  min_replicas=None,
                  max_replicas=None,
                  set_env_vars=None,
                  replace_env_vars=None,
                  remove_env_vars=None,
                  remove_all_env_vars=False,
                  cpu=None,
                  memory=None,
                  revision_suffix=None,
                  startup_command=None,
                  args=None,
                  tags=None,
                  no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    if not name and not from_revision:
        raise RequiredArgumentMissingError('Usage error: --name is required if not using --from-revision.')

    if not name:
        name = _get_app_from_revision(from_revision)

    return update_containerapp_logic(cmd,
                                     name,
                                     resource_group_name,
                                     yaml,
                                     image,
                                     container_name,
                                     min_replicas,
                                     max_replicas,
                                     set_env_vars,
                                     remove_env_vars,
                                     replace_env_vars,
                                     remove_all_env_vars,
                                     cpu,
                                     memory,
                                     revision_suffix,
                                     startup_command,
                                     args,
                                     tags,
                                     no_wait,
                                     from_revision)


def set_revision_mode(cmd, resource_group_name, name, mode, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    containerapp_def["properties"]["configuration"]["activeRevisionsMode"] = mode.lower()

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        return r["properties"]["configuration"]["activeRevisionsMode"]
    except Exception as e:
        handle_raw_exception(e)


def show_ingress(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    try:
        return containerapp_def["properties"]["configuration"]["ingress"]
    except Exception as e:
        raise ValidationError("The containerapp '{}' does not have ingress enabled.".format(name)) from e


def enable_ingress(cmd, name, resource_group_name, type, target_port, transport="auto", allow_insecure=False, disable_warnings=False, no_wait=False):  # pylint: disable=redefined-builtin
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    external_ingress = None
    if type is not None:
        if type.lower() == "internal":
            external_ingress = False
        elif type.lower() == "external":
            external_ingress = True

    ingress_def = None
    if target_port is not None and type is not None:
        ingress_def = IngressModel
        ingress_def["external"] = external_ingress
        ingress_def["targetPort"] = target_port
        ingress_def["transport"] = transport
        ingress_def["allowInsecure"] = allow_insecure

    containerapp_def["properties"]["configuration"]["ingress"] = ingress_def

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        not disable_warnings and logger.warning("\nIngress enabled. Access your app at https://{}/\n".format(r["properties"]["configuration"]["ingress"]["fqdn"]))
        return r["properties"]["configuration"]["ingress"]
    except Exception as e:
        handle_raw_exception(e)


def disable_ingress(cmd, name, resource_group_name, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    containerapp_def["properties"]["configuration"]["ingress"] = None

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    try:
        ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        logger.warning("Ingress has been disabled successfully.")
        return
    except Exception as e:
        handle_raw_exception(e)


def set_ingress_traffic(cmd, name, resource_group_name, traffic_weights, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    try:
        containerapp_def["properties"]["configuration"]["ingress"]
    except Exception as e:
        raise ValidationError("Ingress must be enabled to set ingress traffic. Try running `az containerapp ingress -h` for more info.") from e

    if traffic_weights is not None:
        _update_traffic_weights(containerapp_def, traffic_weights)

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        return r["properties"]["configuration"]["ingress"]["traffic"]
    except Exception as e:
        handle_raw_exception(e)


def show_ingress_traffic(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    try:
        return containerapp_def["properties"]["configuration"]["ingress"]["traffic"]
    except Exception as e:
        raise ValidationError("Ingress must be enabled to show ingress traffic. Try running `az containerapp ingress -h` for more info.") from e


def show_registry(cmd, name, resource_group_name, server):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    try:
        containerapp_def["properties"]["configuration"]["registries"]
    except Exception as e:
        raise ValidationError("The containerapp {} has no assigned registries.".format(name)) from e

    registries_def = containerapp_def["properties"]["configuration"]["registries"]

    for r in registries_def:
        if r['server'].lower() == server.lower():
            return r
    raise InvalidArgumentValueError("The containerapp {} does not have specified registry assigned.".format(name))


def list_registry(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    try:
        return containerapp_def["properties"]["configuration"]["registries"]
    except Exception as e:
        raise ValidationError("The containerapp {} has no assigned registries.".format(name)) from e


def set_registry(cmd, name, resource_group_name, server, username=None, password=None, disable_warnings=False, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    registries_def = None
    registry = None

    if "registries" not in containerapp_def["properties"]["configuration"]:
        containerapp_def["properties"]["configuration"]["registries"] = []

    registries_def = containerapp_def["properties"]["configuration"]["registries"]

    if not username or not password:
        # If registry is Azure Container Registry, we can try inferring credentials
        if '.azurecr.io' not in server:
            raise RequiredArgumentMissingError('Registry username and password are required if you are not using Azure Container Registry.')
        not disable_warnings and logger.warning('No credential was provided to access Azure Container Registry. Trying to look up...')
        parsed = urlparse(server)
        registry_name = (parsed.netloc if parsed.scheme else parsed.path).split('.')[0]

        try:
            username, password, _ = _get_acr_cred(cmd.cli_ctx, registry_name)
        except Exception as ex:
            raise RequiredArgumentMissingError('Failed to retrieve credentials for container registry. Please provide the registry username and password') from ex

    # Check if updating existing registry
    updating_existing_registry = False
    for r in registries_def:
        if r['server'].lower() == server.lower():
            not disable_warnings and logger.warning("Updating existing registry.")
            updating_existing_registry = True
            if username:
                r["username"] = username
            if password:
                r["passwordSecretRef"] = store_as_secret_and_return_secret_ref(
                    containerapp_def["properties"]["configuration"]["secrets"],
                    r["username"],
                    r["server"],
                    password,
                    update_existing_secret=True)

    # If not updating existing registry, add as new registry
    if not updating_existing_registry:
        registry = RegistryCredentialsModel
        registry["server"] = server
        registry["username"] = username
        registry["passwordSecretRef"] = store_as_secret_and_return_secret_ref(
            containerapp_def["properties"]["configuration"]["secrets"],
            username,
            server,
            password,
            update_existing_secret=True)

        registries_def.append(registry)

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)

        return r["properties"]["configuration"]["registries"]
    except Exception as e:
        handle_raw_exception(e)


def remove_registry(cmd, name, resource_group_name, server, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    registries_def = None

    try:
        containerapp_def["properties"]["configuration"]["registries"]
    except Exception as e:
        raise ValidationError("The containerapp {} has no assigned registries.".format(name)) from e

    registries_def = containerapp_def["properties"]["configuration"]["registries"]

    wasRemoved = False
    for i, value in enumerate(registries_def):
        r = value
        if r['server'].lower() == server.lower():
            registries_def.pop(i)
            _remove_registry_secret(containerapp_def=containerapp_def, server=server, username=r["username"])
            wasRemoved = True
            break

    if not wasRemoved:
        raise ValidationError("Containerapp does not have registry server {} assigned.".format(server))

    if len(containerapp_def["properties"]["configuration"]["registries"]) == 0:
        containerapp_def["properties"]["configuration"].pop("registries")

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        logger.warning("Registry successfully removed.")
        return r["properties"]["configuration"]["registries"]
    # No registries to return, so return nothing
    except Exception:
        pass


def list_secrets(cmd, name, resource_group_name, show_values=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        r = containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    if not show_values:
        try:
            return r["properties"]["configuration"]["secrets"]
        except:
            return []
    try:
        return ContainerAppClient.list_secrets(cmd=cmd, resource_group_name=resource_group_name, name=name)["value"]
    except Exception:
        return []
        # raise ValidationError("The containerapp {} has no assigned secrets.".format(name)) from e


def show_secret(cmd, name, resource_group_name, secret_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    r = ContainerAppClient.list_secrets(cmd=cmd, resource_group_name=resource_group_name, name=name)
    for secret in r["value"]:
        if secret["name"].lower() == secret_name.lower():
            return secret
    raise ValidationError("The containerapp {} does not have a secret assigned with name {}.".format(name, secret_name))


def remove_secrets(cmd, name, resource_group_name, secret_names, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    for secret_name in secret_names:
        wasRemoved = False
        for secret in containerapp_def["properties"]["configuration"]["secrets"]:
            if secret["name"].lower() == secret_name.lower():
                _remove_secret(containerapp_def, secret_name=secret["name"])
                wasRemoved = True
                break
        if not wasRemoved:
            raise ValidationError("The containerapp {} does not have a secret assigned with name {}.".format(name, secret_name))
    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        logger.warning("Secret(s) successfully removed.")
        try:
            return r["properties"]["configuration"]["secrets"]
        # No secrets to return
        except:
            pass
    except Exception as e:
        handle_raw_exception(e)


def set_secrets(cmd, name, resource_group_name, secrets,
                # yaml=None,
                no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    # if not yaml and not secrets:
    #     raise RequiredArgumentMissingError('Usage error: --secrets is required if not using --yaml')

    # if not secrets:
    #     secrets = []

    # if yaml:
    #     yaml_secrets = load_yaml_file(yaml).split(' ')
    #     try:
    #         parse_secret_flags(yaml_secrets)
    #     except:
    #         raise ValidationError("YAML secrets must be a list of secrets in key=value format, delimited by new line.")
    #     for secret in yaml_secrets:
    #         secrets.append(secret.strip())

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)
    _add_or_update_secrets(containerapp_def, parse_secret_flags(secrets))

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        logger.warning("Containerapp '{}' must be restarted in order for secret changes to take effect.".format(name))
        return r["properties"]["configuration"]["secrets"]
    except Exception as e:
        handle_raw_exception(e)


def enable_dapr(cmd, name, resource_group_name, dapr_app_id=None, dapr_app_port=None, dapr_app_protocol=None, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    if 'configuration' not in containerapp_def['properties']:
        containerapp_def['properties']['configuration'] = {}

    if 'dapr' not in containerapp_def['properties']['configuration']:
        containerapp_def['properties']['configuration']['dapr'] = {}

    if dapr_app_id:
        containerapp_def['properties']['configuration']['dapr']['appId'] = dapr_app_id

    if dapr_app_port:
        containerapp_def['properties']['configuration']['dapr']['appPort'] = dapr_app_port

    if dapr_app_protocol:
        containerapp_def['properties']['configuration']['dapr']['appProtocol'] = dapr_app_protocol

    containerapp_def['properties']['configuration']['dapr']['enabled'] = True

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        return r["properties"]['configuration']['dapr']
    except Exception as e:
        handle_raw_exception(e)


def disable_dapr(cmd, name, resource_group_name, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    containerapp_def = None
    try:
        containerapp_def = ContainerAppClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except:
        pass

    if not containerapp_def:
        raise ResourceNotFoundError("The containerapp '{}' does not exist".format(name))

    _get_existing_secrets(cmd, resource_group_name, name, containerapp_def)

    if 'configuration' not in containerapp_def['properties']:
        containerapp_def['properties']['configuration'] = {}

    if 'dapr' not in containerapp_def['properties']['configuration']:
        containerapp_def['properties']['configuration']['dapr'] = {}

    containerapp_def['properties']['configuration']['dapr']['enabled'] = False

    try:
        r = ContainerAppClient.create_or_update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, container_app_envelope=containerapp_def, no_wait=no_wait)
        return r["properties"]['configuration']['dapr']
    except Exception as e:
        handle_raw_exception(e)


def list_dapr_components(cmd, resource_group_name, environment_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    return DaprComponentClient.list(cmd, resource_group_name, environment_name)


def show_dapr_component(cmd, resource_group_name, dapr_component_name, environment_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    return DaprComponentClient.show(cmd, resource_group_name, environment_name, name=dapr_component_name)


def create_or_update_dapr_component(cmd, resource_group_name, environment_name, dapr_component_name, yaml):
    _validate_subscription_registered(cmd, "Microsoft.App")

    yaml_containerapp = load_yaml_file(yaml)
    if type(yaml_containerapp) != dict:  # pylint: disable=unidiomatic-typecheck
        raise ValidationError('Invalid YAML provided. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.')

    # Deserialize the yaml into a DaprComponent object. Need this since we're not using SDK
    daprcomponent_def = None
    try:
        deserializer = create_deserializer()

        daprcomponent_def = deserializer('DaprComponent', yaml_containerapp)
    except DeserializationError as ex:
        raise ValidationError('Invalid YAML provided. Please see https://aka.ms/azure-container-apps-yaml for a valid containerapps YAML spec.') from ex

    daprcomponent_def = _convert_object_from_snake_to_camel_case(_object_to_dict(daprcomponent_def))

    # Remove "additionalProperties" and read-only attributes that are introduced in the deserialization. Need this since we're not using SDK
    _remove_additional_attributes(daprcomponent_def)
    _remove_dapr_readonly_attributes(daprcomponent_def)

    if not daprcomponent_def["ignoreErrors"]:
        daprcomponent_def["ignoreErrors"] = False

    dapr_component_envelope = {}

    dapr_component_envelope["properties"] = daprcomponent_def

    try:
        r = DaprComponentClient.create_or_update(cmd, resource_group_name=resource_group_name, environment_name=environment_name, dapr_component_envelope=dapr_component_envelope, name=dapr_component_name)
        return r
    except Exception as e:
        handle_raw_exception(e)


def remove_dapr_component(cmd, resource_group_name, dapr_component_name, environment_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        DaprComponentClient.show(cmd, resource_group_name, environment_name, name=dapr_component_name)
    except Exception as e:
        raise ResourceNotFoundError("Dapr component not found.") from e

    try:
        r = DaprComponentClient.delete(cmd, resource_group_name, environment_name, name=dapr_component_name)
        logger.warning("Dapr componenet successfully deleted.")
        return r
    except Exception as e:
        handle_raw_exception(e)


def list_replicas(cmd, resource_group_name, name, revision=None):
    app = ContainerAppClient.show(cmd, resource_group_name, name)
    if not revision:
        revision = app["properties"]["latestRevisionName"]
    return ContainerAppClient.list_replicas(cmd=cmd,
                                            resource_group_name=resource_group_name,
                                            container_app_name=name,
                                            revision_name=revision)


def get_replica(cmd, resource_group_name, name, replica, revision=None):
    app = ContainerAppClient.show(cmd, resource_group_name, name)
    if not revision:
        revision = app["properties"]["latestRevisionName"]
    return ContainerAppClient.get_replica(cmd=cmd,
                                          resource_group_name=resource_group_name,
                                          container_app_name=name,
                                          revision_name=revision,
                                          replica_name=replica)


# TODO token will be read from header at some point -- a PR has apparently been opened for this
def containerapp_ssh(cmd, resource_group_name, name, container=None, revision=None, replica=None, startup_command="sh"):
    if isinstance(startup_command, list):
        startup_command = startup_command[0]  # CLI seems a little buggy when calling a param "--command"

    conn = WebSocketConnection(cmd=cmd, resource_group_name=resource_group_name, name=name, revision=revision,
                               replica=replica, container=container, startup_command=startup_command)

    encodings = [SSH_DEFAULT_ENCODING, SSH_BACKUP_ENCODING]
    reader = threading.Thread(target=read_ssh, args=(conn, encodings))
    reader.daemon = True
    reader.start()

    writer = get_stdin_writer(conn)
    writer.daemon = True
    writer.start()

    logger.warning("Use ctrl + D to exit.")
    while conn.is_connected:
        try:
            time.sleep(0.1)
        except KeyboardInterrupt:
            if conn.is_connected:
                logger.info("Caught KeyboardInterrupt. Sending ctrl+c to server")
                conn.send(SSH_CTRL_C_MSG)


# TODO token will be in header soon (same as SSH)
def stream_containerapp_logs(cmd, resource_group_name, name, container=None, revision=None, replica=None, follow=False,
                             tail=None, output_format=None):
    if tail:
        if tail < 0 or tail > 300:
            raise ValidationError("--tail must be between 0 and 300.")

    sub = get_subscription_id(cmd.cli_ctx)
    token_response = ContainerAppClient.get_auth_token(cmd, resource_group_name, name)
    token = token_response["properties"]["token"]
    logstream_endpoint = token_response["properties"]["logStreamEndpoint"]
    base_url = logstream_endpoint[:logstream_endpoint.index("/subscriptions/")]

    # TODO remove token from URL once token is read from header
    url = (f"{base_url}/subscriptions/{sub}/resourceGroups/{resource_group_name}/containerApps/{name}"
           f"/revisions/{revision}/replicas/{replica}/containers/{container}/logstream?token={token}")

    logger.warning("connecting to : %s", remove_token(url))
    request_params = {"follow": str(follow).lower(), "output": output_format, "tailLines": tail}
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, timeout=None, stream=True, params=request_params, headers=headers)

    if not resp.ok:
        ValidationError(f"Got bad status from the logstream API: {resp.status_code}")

    for line in resp.iter_lines():
        if line:
            logger.info("received raw log line: %s", line)
            # these .replaces are needed to display color/quotations properly
            # for some reason the API returns garbled unicode special characters (may need to add more in the future)
            print(line.decode("utf-8").replace("\\u0022", "\u0022").replace("\\u001B", "\u001B").replace("\\u002B", "\u002B").replace("\\u0027", "\u0027"))


def open_containerapp_in_browser(cmd, name, resource_group_name):
    app = ContainerAppClient.show(cmd, resource_group_name, name)
    url = safe_get(app, "properties", "configuration", "ingress", "fqdn")
    if not url:
        raise ValidationError("Could not open in browser: no public URL for this app")
    if not url.startswith("http"):
        url = f"http://{url}"
    open_page_in_browser(url)


# up utils -- TODO move to their own file

def _create_service_principal(cmd, resource_group_name, env_resource_group_name):
    logger.warning("No valid service principal provided. Creating a new service principal...")
    scopes = [f"/subscriptions/{get_subscription_id(cmd.cli_ctx)}/resourceGroups/{resource_group_name}"]
    if env_resource_group_name is not None and env_resource_group_name != resource_group_name:
        scopes.append(f"/subscriptions/{get_subscription_id(cmd.cli_ctx)}/resourceGroups/{env_resource_group_name}")
    sp = create_service_principal_for_rbac(cmd, scopes=scopes, role="contributor")

    logger.info(f"Created service principal: {sp['displayName']}")

    return sp["appId"], sp["password"], sp["tenant"]


def _get_or_create_sp(cmd, resource_group_name, env_resource_group_name, name, service_principal_client_id,
                      service_principal_client_secret, service_principal_tenant_id):
    try:
        GitHubActionClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
        return service_principal_client_id, service_principal_client_secret, service_principal_tenant_id
    except:
        service_principal = None

        # TODO if possible, search for SPs with the right credentials
        # I haven't found a way to get SP creds + secrets yet from the API

        if not service_principal:
            return _create_service_principal(cmd, resource_group_name, env_resource_group_name)
        # return client_id, secret, tenant_id


def _get_dockerfile_content_from_repo(repo_url, branch, token, context_path, dockerfile):
    from github import Github
    g = Github(token)
    repo = _repo_url_to_name(repo_url)
    r = g.get_repo(repo)
    files = r.get_contents(context_path, ref=branch)
    for f in files:
        if f.path == dockerfile or f.path.endswith(f"/{dockerfile}"):
            resp = requests.get(f.download_url)
            if resp.ok and resp.content:
                return resp.content.decode("utf-8").split("\n")


def _get_ingress_and_target_port(ingress, target_port, dockerfile_content: 'list[str]'):
    if not target_port and not ingress and dockerfile_content is not None:
        for line in dockerfile_content:
            if line:
                line = line.upper().strip().replace("/TCP", "").replace("/UDP", "").replace("\n","")
                if line and line[0] != "#":
                    if "EXPOSE" in line:
                            parts = line.split(" ")
                            for i, p in enumerate(parts[:-1]):
                                if "EXPOSE" in p and is_int(parts[i+1]):
                                    target_port = parts[i+1]
                                    ingress = "external"
                                    logger.warning("Adding external ingress port {} based on dockerfile expose.".format(target_port))
    ingress = "external" if target_port and not ingress else ingress
    return ingress, target_port


def _validate_up_args(source, image, repo):
    if not source and not image and not repo:
        raise RequiredArgumentMissingError("You must specify either --source, --repo, or --image")
    if source and repo:
        raise MutuallyExclusiveArgumentError("Cannot use --source and --repo togther. "
                                             "Can either deploy from a local directory or a Github repo")

def _reformat_image(source, repo, image):
    if source and (image or repo):
        image = image.split('/')[-1]  # if link is given
        image = image.replace(':', '')
    return image

def _get_dockerfile_content_local(source, dockerfile):
    lines = []
    if source:
        dockerfile_location = f"{source}/{dockerfile}"
        try:
            with open(dockerfile_location, 'r') as fh:
                lines = [line for line in fh]
        except:
            raise InvalidArgumentValueError("Cannot open specified Dockerfile. Check dockerfile name, path, and permissions.")
    return lines


def _get_dockerfile_content(repo, branch, token, source, dockerfile):
    if source:
        return _get_dockerfile_content_local(source, dockerfile)
    return _get_dockerfile_content_from_repo(repo, branch, token)


def _get_app_env_and_group(cmd, name, resource_group: 'ResourceGroup', env: 'ContainerAppEnvironment'):
    if not resource_group.name and not resource_group.exists:
        matched_apps = [c for c in list_containerapp(cmd) if c['name'].lower() == name.lower()]
        if len(matched_apps) == 1:
                if env.name:
                    logger.warning("User passed custom environment name for an existing containerapp. Using existing environment.")
                resource_group.name = matched_apps[0]["resourceGroup"]
                env.name = matched_apps[0]["properties"]["managedEnvironmentId"]
        elif len(matched_apps) > 1:
            raise ValidationError(f"There are multiple containerapps with name {name} on the subscription. "
                                    "Please specify which resource group your Containerapp is in.")


def _get_env_and_group_from_log_analytics(cmd, resource_group_name, env:'ContainerAppEnvironment', resource_group:'ResourceGroup', logs_customer_id, location):
    # resource_group_name is the value the user passed in (if present)
    if not env.name:
        if (resource_group_name == resource_group.name and resource_group.exists) or (not resource_group_name):
            env_list = list_managed_environments(cmd=cmd, resource_group_name=resource_group_name)
            if logs_customer_id:
                env_list = [e for e in env_list if safe_get(e, "properties", "appLogsConfiguration", "logAnalyticsConfiguration", "customerId") == logs_customer_id]
            if location:
                env_list = [e for e in env_list if e['location'] == location]
            if env_list:
                # TODO check how many CA in env
                env_details = parse_resource_id(env_list[0]["id"])
                env.name = env_details["name"]
                resource_group.name = env_details["resource_group"]


def _get_acr_from_image(cmd, app):
    if app.image is not None and "azurecr.io" in app.image:
        if app.registry_user is None or app.registry_pass is None:
            logger.info('No credential was provided to access Azure Container Registry. Trying to look up...')
            app.registry_server = app.image.split('/')[0]  # TODO what if this conflicts with registry_server param?
            parsed = urlparse(app.image)
            registry_name = (parsed.netloc if parsed.scheme else parsed.path).split('.')[0]
        try:
            app.registry_user, app.registry_pass, registry_rg = _get_acr_cred(cmd.cli_ctx, registry_name)
            app.acr = AzureContainerRegistry(registry_name, ResourceGroup(cmd, registry_rg, None, None))
        except Exception as ex:
            raise RequiredArgumentMissingError('Failed to retrieve credentials for container registry. Please provide the registry username and password') from ex


def _get_registry_from_app(app):
    containerapp_def = app.get()
    if containerapp_def:
            if len(safe_get(containerapp_def, "properties", "configuration", "registries")) == 1:
                app.registry_server = containerapp_def["properties"]["configuration"]["registries"][0]["server"]


def _get_registry_details(cmd, app: 'ContainerApp'):
    registry_rg = None
    registry_name = None
    if app.registry_server:
        if "azurecr.io" not in app.registry_server:
            raise ValidationError("Cannot supply non-Azure registry when using --source.")
        if app.registry_user is None or app.registry_pass is None:
            logger.info('No credential was provided to access Azure Container Registry. Trying to look up...')
            parsed = urlparse(app.registry_server)
            registry_name = (parsed.netloc if parsed.scheme else parsed.path).split('.')[0]
            try:
                app.registry_user, app.registry_pass, registry_rg = _get_acr_cred(cmd.cli_ctx, registry_name)
            except Exception as ex:
                raise RequiredArgumentMissingError('Failed to retrieve credentials for container registry. Please provide the registry username and password') from ex
    else:
        registry_rg = app.resource_group.name
        user = get_profile_username()
        registry_name = "{}acr".format(app.name).replace('-','')
        registry_name = registry_name + str(hash((registry_rg, user, app.name))).replace("-", "")
        app.registry_server = registry_name + ".azurecr.io"
        app.should_create_acr = True
    app.acr = AzureContainerRegistry(registry_name, ResourceGroup(cmd, registry_rg, None, None))


class ResourceGroup:
    def __init__(self, cmd, name: str, location: str, exists: bool):
        self.cmd = cmd
        self.name = name
        self.location = _get_default_containerapps_location(cmd, location)
        self.exists = exists

        self.check_exists()

    def create(self, cmd):
        if not self.name:
            self.name = get_randomized_name(get_profile_username())
        g = create_resource_group(cmd, self.name, self.location)
        self.exists = True
        return g

    def _get(self):
        return get_resource_group(self.cmd, self.name)

    def get(self):
        r = None
        try:
            r = self._get(self.cmd)
        except:
            pass
        return r

    def check_exists(self) -> bool:
        self.exists = check_resource_group_exists(self.cmd, self.name)
        return self.exists


class Resource:
    def __init__(self, cmd, name: str, resource_group: 'ResourceGroup', exists: bool=None):
        self.cmd = cmd
        self.name = name
        self.resource_group = resource_group
        self.exists = exists

        self.check_exists(cmd)


    def create(self, *args, **kwargs):
        raise NotImplementedError()

    def _get(self):
        raise NotImplementedError()

    def get(self):
        r = None
        try:
            r = self._get(self.cmd)
        except:
            pass
        return r

    def check_exists(self):
        self.exists = self.get() is None
        return self.exists


class ContainerAppEnvironment(Resource):
    def __init__(self,
                 cmd,
                 name: str,
                 resource_group: 'ResourceGroup',
                 exists: bool=None,
                 location=None,
                 logs_key=None,
                 logs_customer_id=None):

        super().__init__(cmd, name, resource_group, exists)
        if is_valid_resource_id(name):
            self.name = parse_resource_id(name)["name"]
            rg = parse_resource_id(name)["resource_group"]
            if resource_group.name != rg:
                self.resource_group = ResourceGroup(cmd, rg, location)
        self.location=_get_default_containerapps_location(cmd, location)
        self.logs_key=logs_key
        self.logs_customer_id=logs_customer_id

    def _get(self, cmd):
        return ManagedEnvironmentClient.show(cmd, self.resource_group.name, self.name)

    def create(self, cmd, app_name):
        if self.name is None:
            self.name = "{}-env".format(app_name).replace("_", "-")
        env = create_managed_environment(cmd,
                                         self.name,
                                         location=self.location,
                                         resource_group_name=self.resource_group.name,
                                         logs_key=self.logs_key,
                                         logs_customer_id=self.logs_customer_id, disable_warnings=True)
        self.exists = True
        return env


class AzureContainerRegistry(Resource):
    def __init__(self,
                 name: str,
                 resource_group: 'ResourceGroup'):

        self.name = name
        self.resource_group = resource_group


class ContainerApp(Resource):
    def __init__(self,
                 cmd,
                 name: str,
                 resource_group: 'ResourceGroup',
                 exists: bool=None,
                 image=None,
                 env: 'ContainerAppEnvironment'=None,
                 target_port=None,
                 registry_server=None,
                 registry_user=None,
                 registry_pass=None,
                 env_vars=None,
                 ingress=None):

        super().__init__(cmd, name, resource_group, exists)
        self.image=image
        self.env=env
        self.target_port=target_port
        self.registry_server=registry_server
        self.registry_user=registry_user
        self.registry_pass = registry_pass
        self.env_vars=env_vars
        self.ingress=ingress

        self.should_create_acr = False
        self.acr: 'AzureContainerRegistry' = None

    def _get(self, cmd):
        return ContainerAppClient.show(cmd, self.resource_group, self.name)

    def create(self, cmd):
        return create_containerapp(cmd=cmd,
                                   name=self.name,
                                   resource_group_name=self.resource_group.name,
                                   image=self.image,
                                   managed_env=self.env.name,
                                   target_port=self.target_port,
                                   registry_server=self.registry_server,
                                   registry_pass=self.registry_pass,
                                   registry_user=self.registry_user,
                                   env_vars=self.env_vars,
                                   ingress=self.ingress,
                                   disable_warnings=True)
    def create_acr(self):
        registry_rg = self.resource_group.name
        url = self.registry_server
        registry_name = url[:url.rindex(".azurecr.io")]
        registry_def = create_new_acr(self.cmd, registry_name, registry_rg, self.location)
        self.registry_server = registry_def.login_server

    def run_acr_build(self, dockerfile):
        image_name = self.image if self.image is not None else self.name
        from datetime import datetime
        now = datetime.now()
        # Add version tag for acr image
        image_name += ":{}".format(str(now).replace(' ', '').replace('-', '').replace('.', '').replace(':', ''))

        self.registry_rg

        self.image = self.registry_server + '/' + image_name
        queue_acr_build(self.cmd, self.registry_rg, self.registry_name, image_name, self.source, dockerfile, quiet=True)


def containerapp_up(cmd,
                    name,
                    resource_group_name=None,
                    managed_env=None,
                    location=None,
                    registry_server=None,
                    image=None,
                    source=None,
                    ingress=None,
                    target_port=None,
                    registry_user=None,
                    registry_pass=None,
                    env_vars=None,
                    logs_customer_id=None,
                    logs_key=None,
                    repo=None,
                    branch=None,
                    browse=False,
                    context_path=None,
                    service_principal_client_id=None,
                    service_principal_client_secret=None,
                    service_principal_tenant_id=None):
    dockerfile="Dockerfile",  # for now the dockerfile name must be "Dockerfile" (until GH actions API is updated)

    _validate_up_args(source, image, repo)

    image = _reformat_image(source, repo, image)
    token = None if not repo else get_github_access_token(cmd, ["admin:repo_hook", "repo", "workflow"])

    dockerfile_content = _get_dockerfile_content(repo, branch, token, source, dockerfile)
    ingress, target_port = _get_ingress_and_target_port(ingress, target_port, dockerfile_content)

    resource_group = ResourceGroup(name=resource_group_name, location=location)
    env = ContainerAppEnvironment(cmd, managed_env, resource_group, location=location, logs_key=logs_key, logs_customer_id=logs_customer_id)
    app = ContainerApp(cmd, name, resource_group, None, image, env, target_port, registry_server, registry_user, registry_pass, env_vars, ingress)

    # If no RG passed in and a singular app exists with the same name, get its env and rg
    _get_app_env_and_group(cmd, name, resource_group, env)

    # If no env passed in (and not creating a new RG), then try getting an env by location / log analytics ID
    _get_env_and_group_from_log_analytics(cmd, resource_group_name, env, resource_group, logs_customer_id, location)

    # get ACR details from --image, if possible
    _get_acr_from_image(cmd, app)

    if source:
        registry_server = _get_registry_from_app(app)  # if the app exists, get the registry
        _get_registry_details(cmd, app)  # fetch ACR creds from arguments registry arguments

    if not resource_group.check_exists():
        logger.warning(f"Creating resource group {resource_group.name}")
        resource_group.create()
    if not env.check_exists():
        logger.warning(f"Creating Containerapp environment {env.name} in resource group {env.resource_group.name}")
        env.create(name)
    if app._should_create_acr():
        logger.warning(f"Creating Azure Container Registry {app.acr.name} in resource group {app.acr.resource_group.name}")
        app.create_acr()

    if source:
        app.run_acr_build(dockerfile)
        # return image

    logger.warning(f"Creating Containerapp {app.name} in resource group {app.resource_group.name}")
    app.create()

    if repo:
        sp = _get_or_create_sp(cmd,
                               app.resource_group.name,
                               env.resource_group.name,
                               name,
                               service_principal_client_id,
                               service_principal_client_secret,
                               service_principal_tenant_id)
        service_principal_client_id, service_principal_client_secret, service_principal_tenant_id = sp
        gh_action = create_or_update_github_action(cmd=cmd,
                                                   name=name,
                                                   resource_group_name=resource_group_name,
                                                   repo_url=repo,
                                                   registry_url=registry_server,
                                                   registry_username=registry_user,
                                                   registry_password=registry_pass,
                                                   branch=branch,
                                                   token=token,
                                                   login_with_github=False,
                                                   service_principal_client_id=service_principal_client_id,
                                                   service_principal_client_secret=service_principal_client_secret,
                                                   service_principal_tenant_id=service_principal_tenant_id,
                                                   image=image,
                                                   context_path=context_path)

    if browse:
        open_containerapp_in_browser(cmd, name, resource_group)

    # TODO output
