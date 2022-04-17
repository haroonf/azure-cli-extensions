# pylint: disable=too-many-lines
# coding=utf-8
# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# Code generated by Microsoft (R) AutoRest Code Generator.
# Changes may cause incorrect behavior and will be lost if the code is regenerated.
# --------------------------------------------------------------------------
from typing import Any, Callable, Dict, Iterable, Optional, TypeVar

from msrest import Serializer

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceExistsError, ResourceNotFoundError, map_error
from azure.core.paging import ItemPaged
from azure.core.pipeline import PipelineResponse
from azure.core.pipeline.transport import HttpResponse
from azure.core.rest import HttpRequest
from azure.core.tracing.decorator import distributed_trace
from azure.mgmt.core.exceptions import ARMErrorFormat

from .. import models as _models
from .._vendor import _convert_request, _format_url_section
T = TypeVar('T')
JSONType = Any
ClsType = Optional[Callable[[PipelineResponse[HttpRequest, HttpResponse], T, Dict[str, Any]], Any]]

_SERIALIZER = Serializer()
_SERIALIZER.client_side_validation = False

def build_list_request(
    subscription_id: str,
    resource_group_name: str,
    network_manager_name: str,
    *,
    top: Optional[int] = None,
    skip_token: Optional[str] = None,
    **kwargs: Any
) -> HttpRequest:
    api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str

    accept = "application/json"
    # Construct URL
    _url = kwargs.pop("template_url", "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations")  # pylint: disable=line-too-long
    path_format_arguments = {
        "subscriptionId": _SERIALIZER.url("subscription_id", subscription_id, 'str'),
        "resourceGroupName": _SERIALIZER.url("resource_group_name", resource_group_name, 'str'),
        "networkManagerName": _SERIALIZER.url("network_manager_name", network_manager_name, 'str'),
    }

    _url = _format_url_section(_url, **path_format_arguments)

    # Construct parameters
    _query_parameters = kwargs.pop("params", {})  # type: Dict[str, Any]
    _query_parameters['api-version'] = _SERIALIZER.query("api_version", api_version, 'str')
    if top is not None:
        _query_parameters['$top'] = _SERIALIZER.query("top", top, 'int', maximum=20, minimum=1)
    if skip_token is not None:
        _query_parameters['$skipToken'] = _SERIALIZER.query("skip_token", skip_token, 'str')

    # Construct headers
    _header_parameters = kwargs.pop("headers", {})  # type: Dict[str, Any]
    _header_parameters['Accept'] = _SERIALIZER.header("accept", accept, 'str')

    return HttpRequest(
        method="GET",
        url=_url,
        params=_query_parameters,
        headers=_header_parameters,
        **kwargs
    )


def build_get_request(
    subscription_id: str,
    resource_group_name: str,
    network_manager_name: str,
    configuration_name: str,
    **kwargs: Any
) -> HttpRequest:
    api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str

    accept = "application/json"
    # Construct URL
    _url = kwargs.pop("template_url", "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations/{configurationName}")  # pylint: disable=line-too-long
    path_format_arguments = {
        "subscriptionId": _SERIALIZER.url("subscription_id", subscription_id, 'str'),
        "resourceGroupName": _SERIALIZER.url("resource_group_name", resource_group_name, 'str'),
        "networkManagerName": _SERIALIZER.url("network_manager_name", network_manager_name, 'str'),
        "configurationName": _SERIALIZER.url("configuration_name", configuration_name, 'str'),
    }

    _url = _format_url_section(_url, **path_format_arguments)

    # Construct parameters
    _query_parameters = kwargs.pop("params", {})  # type: Dict[str, Any]
    _query_parameters['api-version'] = _SERIALIZER.query("api_version", api_version, 'str')

    # Construct headers
    _header_parameters = kwargs.pop("headers", {})  # type: Dict[str, Any]
    _header_parameters['Accept'] = _SERIALIZER.header("accept", accept, 'str')

    return HttpRequest(
        method="GET",
        url=_url,
        params=_query_parameters,
        headers=_header_parameters,
        **kwargs
    )


def build_create_or_update_request(
    subscription_id: str,
    resource_group_name: str,
    network_manager_name: str,
    configuration_name: str,
    *,
    json: JSONType = None,
    content: Any = None,
    **kwargs: Any
) -> HttpRequest:
    api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str
    content_type = kwargs.pop('content_type', None)  # type: Optional[str]

    accept = "application/json"
    # Construct URL
    _url = kwargs.pop("template_url", "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations/{configurationName}")  # pylint: disable=line-too-long
    path_format_arguments = {
        "subscriptionId": _SERIALIZER.url("subscription_id", subscription_id, 'str'),
        "resourceGroupName": _SERIALIZER.url("resource_group_name", resource_group_name, 'str'),
        "networkManagerName": _SERIALIZER.url("network_manager_name", network_manager_name, 'str'),
        "configurationName": _SERIALIZER.url("configuration_name", configuration_name, 'str'),
    }

    _url = _format_url_section(_url, **path_format_arguments)

    # Construct parameters
    _query_parameters = kwargs.pop("params", {})  # type: Dict[str, Any]
    _query_parameters['api-version'] = _SERIALIZER.query("api_version", api_version, 'str')

    # Construct headers
    _header_parameters = kwargs.pop("headers", {})  # type: Dict[str, Any]
    if content_type is not None:
        _header_parameters['Content-Type'] = _SERIALIZER.header("content_type", content_type, 'str')
    _header_parameters['Accept'] = _SERIALIZER.header("accept", accept, 'str')

    return HttpRequest(
        method="PUT",
        url=_url,
        params=_query_parameters,
        headers=_header_parameters,
        json=json,
        content=content,
        **kwargs
    )


def build_delete_request(
    subscription_id: str,
    resource_group_name: str,
    network_manager_name: str,
    configuration_name: str,
    *,
    force: Optional[bool] = None,
    **kwargs: Any
) -> HttpRequest:
    api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str

    accept = "application/json"
    # Construct URL
    _url = kwargs.pop("template_url", "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations/{configurationName}")  # pylint: disable=line-too-long
    path_format_arguments = {
        "subscriptionId": _SERIALIZER.url("subscription_id", subscription_id, 'str'),
        "resourceGroupName": _SERIALIZER.url("resource_group_name", resource_group_name, 'str'),
        "networkManagerName": _SERIALIZER.url("network_manager_name", network_manager_name, 'str'),
        "configurationName": _SERIALIZER.url("configuration_name", configuration_name, 'str'),
    }

    _url = _format_url_section(_url, **path_format_arguments)

    # Construct parameters
    _query_parameters = kwargs.pop("params", {})  # type: Dict[str, Any]
    _query_parameters['api-version'] = _SERIALIZER.query("api_version", api_version, 'str')
    if force is not None:
        _query_parameters['force'] = _SERIALIZER.query("force", force, 'bool')

    # Construct headers
    _header_parameters = kwargs.pop("headers", {})  # type: Dict[str, Any]
    _header_parameters['Accept'] = _SERIALIZER.header("accept", accept, 'str')

    return HttpRequest(
        method="DELETE",
        url=_url,
        params=_query_parameters,
        headers=_header_parameters,
        **kwargs
    )

class SecurityUserConfigurationsOperations(object):
    """
    .. warning::
        **DO NOT** instantiate this class directly.

        Instead, you should access the following operations through
        :class:`~azure.mgmt.network.v2022_02_01_preview.NetworkManagementClient`'s
        :attr:`security_user_configurations` attribute.
    """

    models = _models

    def __init__(self, *args, **kwargs):
        args = list(args)
        self._client = args.pop(0) if args else kwargs.pop("client")
        self._config = args.pop(0) if args else kwargs.pop("config")
        self._serialize = args.pop(0) if args else kwargs.pop("serializer")
        self._deserialize = args.pop(0) if args else kwargs.pop("deserializer")


    @distributed_trace
    def list(
        self,
        resource_group_name: str,
        network_manager_name: str,
        top: Optional[int] = None,
        skip_token: Optional[str] = None,
        **kwargs: Any
    ) -> Iterable["_models.SecurityUserConfigurationListResult"]:
        """Lists all the network manager security user configurations in a network manager, in a paginated
        format.

        :param resource_group_name: The name of the resource group.
        :type resource_group_name: str
        :param network_manager_name: The name of the network manager.
        :type network_manager_name: str
        :param top: An optional query parameter which specifies the maximum number of records to be
         returned by the server. Default value is None.
        :type top: int
        :param skip_token: SkipToken is only used if a previous operation returned a partial result. If
         a previous response contains a nextLink element, the value of the nextLink element will include
         a skipToken parameter that specifies a starting point to use for subsequent calls. Default
         value is None.
        :type skip_token: str
        :keyword callable cls: A custom type or function that will be passed the direct response
        :return: An iterator like instance of either SecurityUserConfigurationListResult or the result
         of cls(response)
        :rtype:
         ~azure.core.paging.ItemPaged[~azure.mgmt.network.v2022_02_01_preview.models.SecurityUserConfigurationListResult]
        :raises: ~azure.core.exceptions.HttpResponseError
        """
        api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str

        cls = kwargs.pop('cls', None)  # type: ClsType["_models.SecurityUserConfigurationListResult"]
        error_map = {
            401: ClientAuthenticationError, 404: ResourceNotFoundError, 409: ResourceExistsError
        }
        error_map.update(kwargs.pop('error_map', {}))
        def prepare_request(next_link=None):
            if not next_link:
                
                request = build_list_request(
                    subscription_id=self._config.subscription_id,
                    resource_group_name=resource_group_name,
                    network_manager_name=network_manager_name,
                    api_version=api_version,
                    top=top,
                    skip_token=skip_token,
                    template_url=self.list.metadata['url'],
                )
                request = _convert_request(request)
                request.url = self._client.format_url(request.url)

            else:
                
                request = build_list_request(
                    subscription_id=self._config.subscription_id,
                    resource_group_name=resource_group_name,
                    network_manager_name=network_manager_name,
                    api_version=api_version,
                    top=top,
                    skip_token=skip_token,
                    template_url=next_link,
                )
                request = _convert_request(request)
                request.url = self._client.format_url(request.url)
                request.method = "GET"
            return request

        def extract_data(pipeline_response):
            deserialized = self._deserialize("SecurityUserConfigurationListResult", pipeline_response)
            list_of_elem = deserialized.value
            if cls:
                list_of_elem = cls(list_of_elem)
            return deserialized.next_link or None, iter(list_of_elem)

        def get_next(next_link=None):
            request = prepare_request(next_link)

            pipeline_response = self._client._pipeline.run(  # pylint: disable=protected-access
                request,
                stream=False,
                **kwargs
            )
            response = pipeline_response.http_response

            if response.status_code not in [200]:
                map_error(status_code=response.status_code, response=response, error_map=error_map)
                raise HttpResponseError(response=response, error_format=ARMErrorFormat)

            return pipeline_response


        return ItemPaged(
            get_next, extract_data
        )
    list.metadata = {'url': "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations"}  # type: ignore

    @distributed_trace
    def get(
        self,
        resource_group_name: str,
        network_manager_name: str,
        configuration_name: str,
        **kwargs: Any
    ) -> "_models.SecurityUserConfiguration":
        """Retrieves a network manager security user configuration.

        :param resource_group_name: The name of the resource group.
        :type resource_group_name: str
        :param network_manager_name: The name of the network manager.
        :type network_manager_name: str
        :param configuration_name: The name of the network manager Security Configuration.
        :type configuration_name: str
        :keyword callable cls: A custom type or function that will be passed the direct response
        :return: SecurityUserConfiguration, or the result of cls(response)
        :rtype: ~azure.mgmt.network.v2022_02_01_preview.models.SecurityUserConfiguration
        :raises: ~azure.core.exceptions.HttpResponseError
        """
        cls = kwargs.pop('cls', None)  # type: ClsType["_models.SecurityUserConfiguration"]
        error_map = {
            401: ClientAuthenticationError, 404: ResourceNotFoundError, 409: ResourceExistsError
        }
        error_map.update(kwargs.pop('error_map', {}))

        api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str

        
        request = build_get_request(
            subscription_id=self._config.subscription_id,
            resource_group_name=resource_group_name,
            network_manager_name=network_manager_name,
            configuration_name=configuration_name,
            api_version=api_version,
            template_url=self.get.metadata['url'],
        )
        request = _convert_request(request)
        request.url = self._client.format_url(request.url)

        pipeline_response = self._client._pipeline.run(  # pylint: disable=protected-access
            request,
            stream=False,
            **kwargs
        )
        response = pipeline_response.http_response

        if response.status_code not in [200]:
            map_error(status_code=response.status_code, response=response, error_map=error_map)
            raise HttpResponseError(response=response, error_format=ARMErrorFormat)

        deserialized = self._deserialize('SecurityUserConfiguration', pipeline_response)

        if cls:
            return cls(pipeline_response, deserialized, {})

        return deserialized

    get.metadata = {'url': "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations/{configurationName}"}  # type: ignore


    @distributed_trace
    def create_or_update(
        self,
        resource_group_name: str,
        network_manager_name: str,
        configuration_name: str,
        security_user_configuration: "_models.SecurityUserConfiguration",
        **kwargs: Any
    ) -> "_models.SecurityUserConfiguration":
        """Creates or updates a network manager security user configuration.

        :param resource_group_name: The name of the resource group.
        :type resource_group_name: str
        :param network_manager_name: The name of the network manager.
        :type network_manager_name: str
        :param configuration_name: The name of the network manager Security Configuration.
        :type configuration_name: str
        :param security_user_configuration: The security user configuration to create or update.
        :type security_user_configuration:
         ~azure.mgmt.network.v2022_02_01_preview.models.SecurityUserConfiguration
        :keyword callable cls: A custom type or function that will be passed the direct response
        :return: SecurityUserConfiguration, or the result of cls(response)
        :rtype: ~azure.mgmt.network.v2022_02_01_preview.models.SecurityUserConfiguration
        :raises: ~azure.core.exceptions.HttpResponseError
        """
        cls = kwargs.pop('cls', None)  # type: ClsType["_models.SecurityUserConfiguration"]
        error_map = {
            401: ClientAuthenticationError, 404: ResourceNotFoundError, 409: ResourceExistsError
        }
        error_map.update(kwargs.pop('error_map', {}))

        api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str
        content_type = kwargs.pop('content_type', "application/json")  # type: Optional[str]

        _json = self._serialize.body(security_user_configuration, 'SecurityUserConfiguration')

        request = build_create_or_update_request(
            subscription_id=self._config.subscription_id,
            resource_group_name=resource_group_name,
            network_manager_name=network_manager_name,
            configuration_name=configuration_name,
            api_version=api_version,
            content_type=content_type,
            json=_json,
            template_url=self.create_or_update.metadata['url'],
        )
        request = _convert_request(request)
        request.url = self._client.format_url(request.url)

        pipeline_response = self._client._pipeline.run(  # pylint: disable=protected-access
            request,
            stream=False,
            **kwargs
        )
        response = pipeline_response.http_response

        if response.status_code not in [200, 201]:
            map_error(status_code=response.status_code, response=response, error_map=error_map)
            raise HttpResponseError(response=response, error_format=ARMErrorFormat)

        if response.status_code == 200:
            deserialized = self._deserialize('SecurityUserConfiguration', pipeline_response)

        if response.status_code == 201:
            deserialized = self._deserialize('SecurityUserConfiguration', pipeline_response)

        if cls:
            return cls(pipeline_response, deserialized, {})

        return deserialized

    create_or_update.metadata = {'url': "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations/{configurationName}"}  # type: ignore


    @distributed_trace
    def delete(  # pylint: disable=inconsistent-return-statements
        self,
        resource_group_name: str,
        network_manager_name: str,
        configuration_name: str,
        force: Optional[bool] = None,
        **kwargs: Any
    ) -> None:
        """Deletes a network manager security user configuration.

        :param resource_group_name: The name of the resource group.
        :type resource_group_name: str
        :param network_manager_name: The name of the network manager.
        :type network_manager_name: str
        :param configuration_name: The name of the network manager Security Configuration.
        :type configuration_name: str
        :param force: Deletes the resource even if it is part of a deployed configuration. If the
         configuration has been deployed, the service will do a cleanup deployment in the background,
         prior to the delete. Default value is None.
        :type force: bool
        :keyword callable cls: A custom type or function that will be passed the direct response
        :return: None, or the result of cls(response)
        :rtype: None
        :raises: ~azure.core.exceptions.HttpResponseError
        """
        cls = kwargs.pop('cls', None)  # type: ClsType[None]
        error_map = {
            401: ClientAuthenticationError, 404: ResourceNotFoundError, 409: ResourceExistsError
        }
        error_map.update(kwargs.pop('error_map', {}))

        api_version = kwargs.pop('api_version', "2022-02-01-preview")  # type: str

        
        request = build_delete_request(
            subscription_id=self._config.subscription_id,
            resource_group_name=resource_group_name,
            network_manager_name=network_manager_name,
            configuration_name=configuration_name,
            api_version=api_version,
            force=force,
            template_url=self.delete.metadata['url'],
        )
        request = _convert_request(request)
        request.url = self._client.format_url(request.url)

        pipeline_response = self._client._pipeline.run(  # pylint: disable=protected-access
            request,
            stream=False,
            **kwargs
        )
        response = pipeline_response.http_response

        if response.status_code not in [200, 204]:
            map_error(status_code=response.status_code, response=response, error_map=error_map)
            raise HttpResponseError(response=response, error_format=ARMErrorFormat)

        if cls:
            return cls(pipeline_response, None, {})

    delete.metadata = {'url': "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkManagers/{networkManagerName}/securityUserConfigurations/{configurationName}"}  # type: ignore

