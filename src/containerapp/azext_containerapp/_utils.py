# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from distutils.filelist import findall
from azure.cli.core.azclierror import (ResourceNotFoundError, ValidationError)
from azure.cli.core.commands.client_factory import get_subscription_id
from knack.log import get_logger
from msrestazure.tools import parse_resource_id
from urllib.parse import urlparse

from ._clients import ContainerAppClient
from ._client_factory import handle_raw_exception, providers_client_factory, cf_resource_groups, log_analytics_client_factory, log_analytics_shared_key_client_factory

logger = get_logger(__name__)


def _get_location_from_resource_group(cli_ctx, resource_group_name):
    client = cf_resource_groups(cli_ctx)
    group = client.get(resource_group_name)
    return group.location


def _validate_subscription_registered(cmd, resource_provider):
    providers_client = None
    try:
        providers_client = providers_client_factory(cmd.cli_ctx, get_subscription_id(cmd.cli_ctx))
        registration_state = getattr(providers_client.get(resource_provider), 'registration_state', "NotRegistered")

        if not (registration_state and registration_state.lower() == 'registered'):
            raise ValidationError('Subscription is not registered for the {} resource provider. Please run \"az provider register -n {} --wait\" to register your subscription.'.format(
                resource_provider, resource_provider))
    except ValidationError as ex:
        raise ex
    except Exception:
        pass


def _ensure_location_allowed(cmd, location, resource_provider, resource_type):
    providers_client = None
    try:
        providers_client = providers_client_factory(cmd.cli_ctx, get_subscription_id(cmd.cli_ctx))

        if providers_client is not None:
            resource_types = getattr(providers_client.get(resource_provider), 'resource_types', [])
            res_locations = []
            for res in resource_types:
                if res and getattr(res, 'resource_type', "") == resource_type:
                    res_locations = getattr(res, 'locations', [])

            res_locations = [res_loc.lower().replace(" ", "").replace("(", "").replace(")", "") for res_loc in res_locations if res_loc.strip()]

            location_formatted = location.lower().replace(" ", "")
            if location_formatted not in res_locations:
                raise ValidationError("Location '{}' is not currently supported. To get list of supported locations, run `az provider show -n {} --query \"resourceTypes[?resourceType=='{}'].locations\"`".format(
                    location, resource_provider, resource_type))
    except ValidationError as ex:
        raise ex
    except Exception:
        pass


def parse_env_var_flags(env_list, is_update_containerapp=False):
    env_pairs = {}

    for pair in env_list:
        key_val = pair.split('=', 1)
        if len(key_val) != 2:
            if is_update_containerapp:
                raise ValidationError("Environment variables must be in the format \"<key>=<value>,<key>=secretref:<value>,...\". If you are updating a Containerapp, did you pass in the flag \"--environment\"? Updating a containerapp environment is not supported, please re-run the command without this flag.")
            raise ValidationError("Environment variables must be in the format \"<key>=<value>,<key>=secretref:<value>,...\".")
        if key_val[0] in env_pairs:
            raise ValidationError("Duplicate environment variable {env} found, environment variable names must be unique.".format(env = key_val[0]))
        value = key_val[1].split('secretref:')
        env_pairs[key_val[0]] = value

    env_var_def = []
    for key, value in env_pairs.items():
        if len(value) == 2:
            env_var_def.append({
                "name": key,
                "secretRef": value[1]
            })
        else:
            env_var_def.append({
                "name": key,
                "value": value[0]
            })

    return env_var_def


def parse_secret_flags(secret_list):
    secret_pairs = {}

    for pair in secret_list:
        key_val = pair.split('=', 1)
        if len(key_val) != 2:
            raise ValidationError("--secrets: must be in format \"<key>=<value>,<key>=<value>,...\"")
        if key_val[0] in secret_pairs:
            raise ValidationError("--secrets: duplicate secret {secret} found, secret names must be unique.".format(secret = key_val[0]))
        secret_pairs[key_val[0]] = key_val[1]

    secret_var_def = []
    for key, value in secret_pairs.items():
        secret_var_def.append({
            "name": key,
            "value": value
        })

    return secret_var_def


def store_as_secret_and_return_secret_ref(secrets_list, registry_user, registry_server, registry_pass, update_existing_secret=False):
    if registry_pass.startswith("secretref:"):
        # If user passed in registry password using a secret

        registry_pass = registry_pass.split("secretref:")
        if len(registry_pass) <= 1:
            raise ValidationError("Invalid registry password secret. Value must be a non-empty value starting with \'secretref:\'.")
        registry_pass = registry_pass[1:]
        registry_pass = ''.join(registry_pass)

        if not any(secret for secret in secrets_list if secret['name'].lower() == registry_pass.lower()):
            raise ValidationError("Registry password secret with name '{}' does not exist. Add the secret using --secrets".format(registry_pass))

        return registry_pass
    else:
        # If user passed in registry password
            if (urlparse(registry_server).hostname is not None):
                registry_secret_name = "{server}-{user}".format(server=urlparse(registry_server).hostname.replace('.', ''), user=registry_user.lower())
            else:
                registry_secret_name = "{server}-{user}".format(server=registry_server.replace('.', ''), user=registry_user.lower())
            
            for secret in secrets_list:
                if secret['name'].lower() == registry_secret_name.lower():
                    if secret['value'].lower() != registry_pass.lower():
                        if update_existing_secret:
                            secret['value'] = registry_pass
                        else:
                            raise ValidationError('Found secret with name \"{}\" but value does not equal the supplied registry password.'.format(registry_secret_name))
                    return registry_secret_name

            logger.warning('Adding registry password as a secret with name \"{}\"'.format(registry_secret_name))
            secrets_list.append({
                "name": registry_secret_name,
                "value": registry_pass
            })

            return registry_secret_name


def parse_list_of_strings(comma_separated_string):
    comma_separated = comma_separated_string.split(',')
    return [s.strip() for s in comma_separated]


def _get_default_log_analytics_location(cmd):
    default_location = "eastus"
    providers_client = None
    try:
        providers_client = providers_client_factory(cmd.cli_ctx, get_subscription_id(cmd.cli_ctx))
        resource_types = getattr(providers_client.get("Microsoft.OperationalInsights"), 'resource_types', [])
        res_locations = []
        for res in resource_types:
            if res and getattr(res, 'resource_type', "") == "workspaces":
                res_locations = getattr(res, 'locations', [])

        if len(res_locations):
            location = res_locations[0].lower().replace(" ", "").replace("(", "").replace(")", "")
            if location:
                return location

    except Exception:
        return default_location
    return default_location

# Generate random 4 character string
def _new_tiny_guid():
    import random, string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=4))

# Follow same naming convention as Portal
def _generate_log_analytics_workspace_name(resource_group_name):
    import re
    prefix = "workspace"
    suffix = _new_tiny_guid()
    alphaNumericRG = resource_group_name
    alphaNumericRG = re.sub(r'[^0-9a-z]', '', resource_group_name)
    maxLength = 40

    name = "{}-{}{}".format(
        prefix,
        alphaNumericRG,
        suffix
    )

    if len(name) > maxLength:
        name = name[:maxLength]
    return name


def _generate_log_analytics_if_not_provided(cmd, logs_customer_id, logs_key, location, resource_group_name):
    if logs_customer_id is None and logs_key is None:
        logger.warning("No Log Analytics workspace provided.")
        try:
            _validate_subscription_registered(cmd, "Microsoft.OperationalInsights")
            log_analytics_client = log_analytics_client_factory(cmd.cli_ctx)
            log_analytics_shared_key_client = log_analytics_shared_key_client_factory(cmd.cli_ctx)

            log_analytics_location = location
            try:
                _ensure_location_allowed(cmd, log_analytics_location, "Microsoft.OperationalInsights", "workspaces")
            except Exception:
                log_analytics_location = _get_default_log_analytics_location(cmd)

            from azure.cli.core.commands import LongRunningOperation
            from azure.mgmt.loganalytics.models import Workspace

            workspace_name = _generate_log_analytics_workspace_name(resource_group_name)
            workspace_instance = Workspace(location=log_analytics_location)
            logger.warning("Generating a Log Analytics workspace with name \"{}\"".format(workspace_name))

            poller = log_analytics_client.begin_create_or_update(resource_group_name, workspace_name, workspace_instance)
            log_analytics_workspace = LongRunningOperation(cmd.cli_ctx)(poller)

            logs_customer_id = log_analytics_workspace.customer_id
            logs_key = log_analytics_shared_key_client.get_shared_keys(
                workspace_name=workspace_name,
                resource_group_name=resource_group_name).primary_shared_key

        except Exception as ex:
            raise ValidationError("Unable to generate a Log Analytics workspace. You can use \"az monitor log-analytics workspace create\" to create one and supply --logs-customer-id and --logs-key")
    elif logs_customer_id is None:
        raise ValidationError("Usage error: Supply the --logs-customer-id associated with the --logs-key")
    elif logs_key is None: # Try finding the logs-key
        log_analytics_client = log_analytics_client_factory(cmd.cli_ctx)
        log_analytics_shared_key_client = log_analytics_shared_key_client_factory(cmd.cli_ctx)

        log_analytics_name = None
        log_analytics_rg = None
        log_analytics = log_analytics_client.list()

        for la in log_analytics:
            if la.customer_id and la.customer_id.lower() == logs_customer_id.lower():
                log_analytics_name = la.name
                parsed_la = parse_resource_id(la.id)
                log_analytics_rg = parsed_la['resource_group']

        if log_analytics_name is None:
            raise ValidationError('Usage error: Supply the --logs-key associated with the --logs-customer-id')

        shared_keys = log_analytics_shared_key_client.get_shared_keys(workspace_name=log_analytics_name, resource_group_name=log_analytics_rg)

        if not shared_keys or not shared_keys.primary_shared_key:
            raise ValidationError('Usage error: Supply the --logs-key associated with the --logs-customer-id')

        logs_key = shared_keys.primary_shared_key

    return logs_customer_id, logs_key


def _get_existing_secrets(cmd, resource_group_name, name, containerapp_def):
    if "secrets" not in containerapp_def["properties"]["configuration"]:
        containerapp_def["properties"]["configuration"]["secrets"] = []
    else:
        secrets = []
        try:
            secrets = ContainerAppClient.list_secrets(cmd=cmd, resource_group_name=resource_group_name, name=name)
        except Exception as e:
            handle_raw_exception(e)

        containerapp_def["properties"]["configuration"]["secrets"] = secrets["value"]
