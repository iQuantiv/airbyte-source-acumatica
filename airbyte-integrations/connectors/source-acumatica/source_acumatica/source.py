#
# Copyright (c) 2024 Airbyte, Inc., all rights reserved.
#


from abc import ABC
import collections
import copy
import datetime
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple, Union
from urllib.parse import urljoin
from dateutil.parser import parse
import requests
import xml.etree.ElementTree as ET
import json
import yaml


import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.core import StreamData
from airbyte_cdk.sources.streams.http import HttpStream,HttpClient
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator

import logging
logger = logging.getLogger("airbyte")

# Basic full refresh stream
class AcumaticaStream(Stream, ABC):

    def __init__(self,name:str,endpointtype:str,config: Mapping[str, Any],schema: dict[str,Any],primary_key:Optional[Union[str, List[str], List[List[str]]]], authenticator = None):
        super().__init__()
        self.config=config
        self._exit_on_rate_limit: bool = False
        self._schema=schema
        self._primary_key=primary_key
        self._name=name
        self._endpointtype=endpointtype
        self._http_client = HttpClient(
            name=self.name,
            logger=self.logger,
            authenticator=authenticator
        )

    @property
    def name(self):
        return self._endpointtype + "__" + self._name
    @property
    def primary_key(self) -> Optional[Union[str, List[str], List[List[str]]]]:
        return self._primary_key
    @property
    def url_base(self):
        if(self._endpointtype=="contract"):
            return self.config["BASEURL"] + "/entity/Default/23.200.001/"
        elif(self._endpointtype=="DAC"):
            return self.config["BASEURL"] + "/odatav4/" + self.config["TENANTNAME"] + "/"
        else:
            return self.config["BASEURL"]

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return self._name

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """
        TODO: Override this method to define a pagination strategy. If you will not be using pagination, no action is required - just return None.

        This method should return a Mapping (e.g: dict) containing whatever information required to make paginated requests. This dict is passed
        to most other methods in this class to help you form headers, request bodies, query params, etc..

        For example, if the API accepts a 'page' parameter to determine which page of the result to return, and a response from the API contains a
        'page' number, then this method should probably return a dict {'page': response.json()['page'] + 1} to increment the page count by 1.
        The request_params method should then read the input next_page_token and set the 'page' param to next_page_token['page'].

        :param response: the most recent response from the API
        :return If there is another page in the result, a mapping (e.g: dict) containing information needed to query the next page in the response.
                If there are no more pages in the result, return None.
        """
        return None
    
    def get_json_schema(self):
        return self._schema

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        if(stream_state):
            query=f"{self.cursor_field} gt datetimeoffset'{stream_state.get(self.cursor_field)}'"
            #logger.info(f"Request Params - Query: {query}")
        #logger.info(f"{inspect.stack()}")
            return {"$filter":query}
        return {}

    def request_headers(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
        ) -> Mapping[str, Any]:
        return {"Accept":"application/json",
                "Content-Type":"application/json",
                'Cache-Control': 'no-cache',
                'Connection': 'Close'}
    
    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: Optional[List[str]] = None,
        stream_slice: Optional[Mapping[str, Any]] = None,
        stream_state: Optional[Mapping[str, Any]] = None,
    )-> Iterable[StreamData]:
        urlpath=urljoin(
                self.url_base,
                self.path(stream_state=stream_state, stream_slice=stream_slice),
            )
        
        try:
            requestparams=self.request_params(stream_state=stream_state,stream_slice=stream_slice)
            logger.info(f"Sending request to {urlpath} with params: {requestparams}")
            _,response = self._http_client.send_request(http_method="GET"
                                                            ,url=urlpath
                                                            ,request_kwargs={}
                                                            ,headers=self.request_headers(stream_state=stream_state,stream_slice=stream_slice)
                                                            ,params=requestparams)
            flattenedjsonvals=[]
            if(response.status_code==200 and len(response.content)>0):
                responsejson=response.json()
                if("@odata.context" in responsejson):
                    flattenedjsonvals=flatten_json_array(responsejson["value"])
                else:
                    flattenedjsonvals=flatten_json_array(responsejson)
            yield from flattenedjsonvals
        except Exception as ex:
            logger.error(ex)
        else:
            logoutFromAcumatica(httpclient=self._http_client,config=self.config)


# Basic incremental stream
class IncrementalAcumaticaStream(AcumaticaStream, ABC):
    def __init__(self,name:str,endpointtype:str,config: Mapping[str, Any],schema: dict[str,Any],primary_key:Optional[Union[str, List[str], List[List[str]]]],cursor_field:str,authenticator = None):
        super().__init__(name=name,endpointtype=endpointtype,config=config,schema=schema,primary_key=primary_key,authenticator=authenticator)
        self._cursor_field=cursor_field

    state_checkpoint_interval = 10
    
    @property
    def cursor_field(self) -> str:
    #     """
    #     TODO
    #     Override to return the cursor field used by this stream e.g: an API entity might always use created_at as the cursor field. This is
    #     usually id or date based. This field's presence tells the framework this in an incremental stream. Required for incremental.

    #     :return str: The name of the cursor field.
    #     """
        return self._cursor_field

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        #If the pull dies midway and the records are not in order by last modified than this may make it so we lose records on restart.
        current_cursor_value=parse(current_stream_state[self.cursor_field]) if self.cursor_field in current_stream_state else parse(latest_record[self.cursor_field])
        latest_cursor_value=parse(latest_record[self.cursor_field])
        #TODO: Handle other cursor values than dates
        if(latest_cursor_value>current_cursor_value):
            new_stream_state=dict(current_stream_state)
            new_stream_state[self.cursor_field]=latest_cursor_value
            return new_stream_state
        elif(current_stream_state=={}):
            return {self.cursor_field:latest_cursor_value}
        else:
            return current_stream_state
    
# Source
class SourceAcumatica(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        TODO: Implement a connection check to validate that the user-provided config can be used to connect to the underlying API

        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
        # Acumatica OAuth2 credentials
        token = get_access_token(config)
        if token != None:
            return True, None  
        return False, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        TODO: Replace the streams below with your own streams.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        accesstoken=get_access_token(config)
        auth = TokenAuthenticator(token=accesstoken)  # Oauth2Authenticator is also available if you need oauth support
        self.http_client = HttpClient(
            name="StreamClient",
            logger=logger,
            authenticator=auth
        )
        #Get the contract based schemas
        
        streams=[]
        # Contract Based Streams
        contractschemas = getmetatdata(httpclient=self.http_client,config=config)
        streams.extend(self.getStreams(config, "contract", auth, contractschemas))


        #Odatav4 (DAC) Based Streams
        odata4schemas=getodata4metadata(httpclient=self.http_client,config=config)
        streams.extend(self.getStreams(config,"DAC", auth, odata4schemas))

        return streams

    def getStreams(self, config, endpointtype, auth, schemas):
        returnStreams=[]
        for fullschemaname in schemas.keys():            
            schemaobject=schemas[fullschemaname]
            schemaname=schemaobject["schemaname"]
            schema=schemaobject["schema"]
            cursorfield=get_first_existing_property_name(schema["properties"],["LastModified","LastModifiedDateTime"])
            primaryKey=schemaobject.get("primarykey","id")
            if cursorfield:
                stream=IncrementalAcumaticaStream(name=schemaname,endpointtype=endpointtype,authenticator=auth,config=config,schema=schema,primary_key=primaryKey,cursor_field=cursorfield)
                returnStreams.append(stream)
            else:
                stream=AcumaticaStream(name=schemaname,endpointtype=endpointtype,authenticator=auth,config=config,schema=schema,primary_key=primaryKey)
                returnStreams.append(stream)
        return returnStreams

def process_schema(schema,depth):
    if isinstance(schema, dict):
        if "allOf" in schema and depth==0:
            # Process and merge schemas in 'allOf'
            merged_schema = {}
            for subschema in schema["allOf"]:
                processed_subschema = process_schema(subschema,depth+1)
                if processed_subschema:
                    if processed_subschema.get("type") == "object" and "properties" in processed_subschema:
                        if "type" not in merged_schema:
                            merged_schema["type"] = "object"
                            merged_schema["properties"] = {}
                        merged_schema["properties"].update(processed_subschema["properties"])
            return merged_schema if merged_schema else None
        elif "allOf" in schema and depth>0:
            return None
        elif schema.get("type") == "object" and depth==1:
            new_properties = {}
            for prop_name, prop_schema in schema.get("properties", {}).items():
                processed_prop = process_schema(prop_schema,depth+1)
                if processed_prop is not None:
                    new_properties[prop_name] = processed_prop
            # Return the object if it has properties
            if new_properties:
                return {'type': 'object', 'properties': new_properties}
            else:
                return None
        elif schema.get("type") == "object" and depth>1:
            properties=schema.get("properties",{})
            if set(properties.keys()) <= {"value", "error"} and "value" in properties:
                # Process object properties
                return properties["value"]
            else:
                return None
        elif schema.get("type") == "array":
            # Exclude arrays
            return None
        else:
            # Return other types as is
            return schema
    else:
        return None

def get_first_existing_property_name(obj, property_names):
    for name in property_names:
        if isinstance(obj, dict) and name in obj:
            return name
        elif hasattr(obj, name):
            return name
    return None

def flatten_value_error(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            properties = schema["properties"]
            # Check if properties only contain 'value' and/or 'error'
            if set(properties.keys()) <= {"value", "error"} and "value" in properties:
                # Replace the object with its 'value' property
                return flatten_value_error(properties["value"])
            else:
                # Recursively process each property
                new_properties = {}
                for prop_name, prop_schema in properties.items():
                    # Exclude arrays
                    if prop_schema.get("type") == "array":
                        continue
                    processed_prop = flatten_value_error(prop_schema)
                    if processed_prop is not None:
                        new_properties[prop_name] = processed_prop
                if new_properties:
                    schema_copy = schema.copy()
                    schema_copy["properties"] = new_properties
                    return schema_copy
                else:
                    return None
        else:
            # For other types, return the schema as is
            return schema
    else:
        return schema

def resolve_refs(schema, definitions):
    """
    Recursively replace $ref in the schema with the actual definition from the definitions section.
    """
    if isinstance(schema, dict):
        # Check if there's a $ref key in the current schema
        if '$ref' in schema:
            ref_name = schema['$ref'].split('/')[-1]
            if ref_name in definitions:
                # Replace the $ref with a deep copy of the referenced definition to avoid modification of the original
                return resolve_refs(copy.deepcopy(definitions[ref_name]), definitions)
        else:
            # Recursively resolve $ref in properties and items
            for key, value in schema.items():
                schema[key] = resolve_refs(value, definitions)
    elif isinstance(schema, list):
        # Recursively resolve $ref in list items
        schema = [resolve_refs(item, definitions) for item in schema]

    return schema

def getmetatdata(httpclient:HttpClient, config):
#Get the entities from metadata and generate the schemas
        headers= {#'User-Agent': 'python-requests/2.32.3'
          'Accept': 'application/json'
          , 'Connection': 'Close'
          , 'Content-Type': 'application/json'
          , 'Cache-Control': 'no-cache'}
        metadataurl=urljoin(config["BASEURL"],"/entity/Default/23.200.001/swagger.json")
        _,swaggerresponse = httpclient.send_request(http_method="GET",request_kwargs={},url=metadataurl,headers=headers)
        swaggerjson=swaggerresponse.json()
        logoutFromAcumatica(httpclient,config)
        return extract_get_schemas(swaggerjson)

def getodata4metadata(httpclient:HttpClient, config):
#Get the entities from metadata and generate the schemas
        headers= {#'User-Agent': 'python-requests/2.32.3'
          'Accept': 'application/json'
          , 'Connection': 'Close'
          , 'Content-Type': 'application/json'
          , 'Cache-Control': 'no-cache'}
        tenantname=config["TENANTNAME"]
        metadataurl=urljoin(config["BASEURL"],f"/ODatav4/{tenantname}/$metadata")
        _,metadataresponse = httpclient.send_request(http_method="GET",request_kwargs={},url=metadataurl,headers=headers)
        odata4xml=metadataresponse.text
        logoutFromAcumatica(httpclient,config)
        return odata_xml_to_json_schema(odata4xml)

def odata_xml_to_json_schema(xml_string):
    # Parse the XML string
    root = ET.fromstring(xml_string)

    # Define namespaces
    namespaces = {
        'edmx': 'http://docs.oasis-open.org/odata/ns/edmx',
        'edm': 'http://docs.oasis-open.org/odata/ns/edm'
    }
    
    # Find edmx:DataServices node
    data_services = root.find('edmx:DataServices',namespaces)
    if data_services is None:
        print("No edmx:DataServices node found")
        return {}

    # Build a mapping from EntityType names to their definitions
    entity_types = {}
    for schema in data_services.findall('edm:Schema',namespaces):
        namespace_attr = schema.get('Namespace')
        for entity_type in schema.findall('edm:EntityType',namespaces):
            name = entity_type.get('Name')
            full_name = f"{namespace_attr}.{name}"
            entity_types[full_name] = entity_type

    # Find the EntitySets
    entity_sets = {}
    for schema in data_services.findall('edm:Schema',namespaces):
        for entity_container in schema.findall('edm:EntityContainer',namespaces):
            for entity_set in entity_container.findall('edm:EntitySet',namespaces):
                name = entity_set.get('Name')
                entity_type = entity_set.get('EntityType')
                entity_sets[name] = entity_type

    # For each EntitySet, generate the JSON schema
    schemas = {}
    for entity_set_name, entity_type_full_name in entity_sets.items():
        entity_type = entity_types.get(entity_type_full_name)
        if not entity_type:
            continue
        streamdata={
            'schema':{},
            'primarykey':[],
            'schemaname':entity_set_name
        }
        # Build the JSON schema
        schema = { 
            'type': 'object',
            'properties': {},
            'required': [],
        }

        # Find the Key properties
        key_elements = entity_type.find('edm:Key',namespaces)
        keys = []
        if key_elements is not None:
            for prop_ref in key_elements.findall('edm:PropertyRef',namespaces):
                key_name = prop_ref.get('Name')
                keys.append(key_name)

        # Process Properties
        for prop in entity_type.findall('edm:Property',namespaces):
            prop_name = prop.get('Name')
            prop_type = prop.get('Type')
            json_type = map_edm_to_json_type(prop_type)
            nullable = prop.get('Nullable', 'true').lower() == 'true'

            schema['properties'][prop_name] = {
                'type': json_type
            }

            # Add to required if it is a key or not nullable
            if prop_name in keys or not nullable:
                schema['required'].append(prop_name)
        streamdata["primarykey"]=keys
        streamdata["schema"]=schema
        fullschemaname="DAC__" + entity_set_name
        schemas[fullschemaname] = streamdata

    return schemas

def map_edm_to_json_type(edm_type):
    # Simple mapping from EDM types to JSON Schema types
    edm_to_json_type_map = {
        'Edm.String': 'string',
        'Edm.Int16': 'integer',
        'Edm.Int32': 'integer',
        'Edm.Int64': 'integer',
        'Edm.Boolean': 'boolean',
        'Edm.Decimal': 'number',
        'Edm.Double': 'number',
        'Edm.Single': 'number',
        'Edm.DateTimeOffset': 'string',
        'Edm.Guid': 'string',
        'Edm.Binary': 'string',
        'Edm.TimeOfDay': 'string',
        'Edm.Date': 'string',
        'Edm.Byte': 'integer',
        'Edm.SByte': 'integer',
        # Add more mappings as needed
    }
    # Handle collection types
    if edm_type.startswith('Collection('):
        item_type = edm_type[11:-1]
        return {
            'type': 'array',
            'items': {
                'type': edm_to_json_type_map.get(item_type, 'string')
            }
        }
    return edm_to_json_type_map.get(edm_type, 'string')

def logoutFromAcumatica(httpclient:HttpClient,config):
        headers= {#'User-Agent': 'python-requests/2.32.3'
          'Accept': 'application/json'
          , 'Connection': 'Close'
          , 'Content-Type': 'application/json'
          , 'Cache-Control': 'no-cache'}
        logouturl=urljoin(config["BASEURL"],'/entity/auth/logout')
        _,logoutresponse=httpclient.send_request(http_method="POST",url=logouturl,request_kwargs={},headers=headers,data={})
        if logoutresponse.ok:
            logger.info("Logged Out")
        else:
            logger.info("Did not log out")

def extract_get_schemas(swagger_json):
    # Load the Swagger file (YAML or JSON)
    swagger_spec = swagger_json

    paths = swagger_spec.get('paths', {})
    definitions = swagger_spec.get('definitions', {})
    get_schemas = {}

    for path, methods in paths.items():
        if 'get' in methods and len(path.split("/"))==2:
            get_method = methods['get']
            responses = get_method.get('responses', {})
            if '200' in responses:
                schema = responses['200'].get('schema', {})
                if schema:
                    # Resolve any $ref within the schema
                    resolved_schema = resolve_refs(schema, definitions)
                    entity_name = path.strip('/').replace('/', '_')
                    flattened_schema=process_schema(resolved_schema["items"],0)
                    fullentityname="contract__"+entity_name
                    get_schemas[fullentityname] = {'schema':flattened_schema,'schemaname':entity_name}

    return get_schemas
    
def get_access_token(config):
    client_id = config["CLIENTID"]
    client_secret = config["CLIENTSECRET"]
    username = config["USERNAME"]
    password = config["PASSWORD"]
    scope = 'api offline_access'
    grant_type = 'password'
    token_url = f'{config["BASEURL"]}/identity/connect/token'
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': grant_type,
        'username': username,
        'password': password,
        'scope': scope
    }
    
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        token = response.json()['access_token']
        print("Access token obtained successfully!")
        return token
    else:
        raise Exception(f"Failed to obtain access token: {response.status_code}, {response.text}")

def flatten_json(nested_json, parent_key='', separator='_'):
        items = []
        for key, value in nested_json.items():
            new_key = f"{parent_key}{separator}{key}" if parent_key else key
            
            if isinstance(value, collections.abc.MutableMapping):
                if 'value' in value:
                    items.append((new_key, value['value']))
                else:
                    items.extend(flatten_json(value, new_key, separator=separator).items())
            else:
                items.append((new_key, value))
        
        return dict(items)

def flatten_json_array(json_array):
    return [flatten_json(item) for item in json_array]


