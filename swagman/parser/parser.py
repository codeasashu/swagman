import re
import os
import jsonpath_rw
import jsonschema
import json
from .pmrequest import pmrequest
from .pmresponse import pmresponse
from .pmschema import pmschema

# https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#dataTypeFormat
python2schematypes = {
    int: ('integer', 'int32'),
    list: ('array', None),
    str: ('string', None),
    bool: ('boolean', "null"),
    dict: ('object', None),
}

class PostmanParser(object):
    IGNOREPROP =  '__IGNOREPROPSWAGMAN'
    IGNOREPROPKEYVAL =  '__IGNOREPROPSWAGMANKEYVAL'

    DEFAULT_PM_SCHEMA = '2.1.0.json'

    def __init__(self, jsoncollection):
        self.pmcollection = jsoncollection
        self.validateSchema()

    def validateSchema(self):
        schemaVer = self.schemaVersion.replace('v', '')
        schemaPath = os.path.realpath(
            os.path.join(os.getcwd(), os.path.dirname(__file__), '..'))
        with open(f'{schemaPath}/schema/{schemaVer}.json') as f:
            try:
                schema = json.load(f)
            except Exception:
                return True
        if schema:
            jsonschema.validate(instance=self.pmcollection, schema=schema)

    @property
    def schemaVersion(self):
        search = re.search('^http[s].\/\/.*\/(.*)\/collection\.json', self.schema)
        if search and search.group(1):
            return  search.group(1)
        return None

    @classmethod
    def getArrayTypes(cls, items):
        types = set()
        for item in items:
            (_type, _) = python2schematypes[type(item)]
            types.add(_type)
        return list(types)

    @classmethod
    def schemawalker(cls, item):
        if item is None:
            return dict(type = 'string', nullable=True)
        (_type, _format) = python2schematypes[type(item)]
        schema = dict(type = _type)
        if isinstance(item, str):
            if item is cls.IGNOREPROP:
                schema = dict(additionalProperties = {})
        if isinstance(item, dict):
            schema['properties'] = dict()
            if(len(item.keys()) > 0):
                schema['required'] = []
            for k, v in item.items():
                if v is cls.IGNOREPROPKEYVAL:
                    schema['properties']['additionalProperties'] = {}
                else:
                    schema['required'].append(k)
                    schema['properties'][k] = cls.schemawalker(v)
        elif isinstance(item, int):
            schema['format'] = _format
        elif isinstance(item, list):
            types = cls.getArrayTypes(item)
            schema['items'] = dict()
            if len(types) is 0:
                schema['items'] = {}
            elif len(types) > 1:
                schema['items']['allOf'] = [cls.schemawalker(v) for v in item]
            else:
                schema['items'] = cls.schemawalker(item[0])
        return schema

    @property
    def title(self):
        return self.pmcollection['info'].get('name', '')
    
    @property
    def schema(self):
        return self.pmcollection['info'].get('schema', self.DEFAULT_PM_SCHEMA)

    @property
    def description(self):
        return self.pmcollection['info'].get('description', 'TODO: Add Description')

    @property
    def version(self):
        return self.pmcollection['info'].get('version', '1.0.0')

    @property
    #@TODO Add more concrete way to look for base host
    def host(self):
        return 'example.com'

    @property
    def basepath(self):
        return '/'

    @property
    def schemes(self):
        return ['http']

    @classmethod
    def camelize(cls, string):
        return ''.join(a.capitalize() for a in re.split('([^a-zA-Z0-9])', string) if a.isalnum())

    @classmethod
    def walker(cls, content, key=None, modifier=None, filter_=None):
        collectitem = dict()
        for item in content:
            if 'item' in item:
                collectitem = cls.walker(item['item'], key, modifier, filter_)
            else:
                #@TODO replace template with env vars if found
                item = cls.replaceenv(item)
                key = key(item) if callable(key) is True else key
                usekey = pmrequest(item['request']).getUri() if key is None else key
                item['key'] = usekey
                collectitem[usekey] = dict(
                    request = cls.requestParser(item),
                    responses = cls.responseParser(item)
                 ) if modifier is None else modifier(item)

                if filter_ and (filter_(collectitem) is True):
                    return collectitem.get(usekey, None)
        return collectitem

    @classmethod
    def replaceenv(cls, item):
        # cls.environemtfile
        return item

    @staticmethod
    def pathParser(item):
        return item['request']['url']['raw']

    @staticmethod
    def requestParser(item):
        return pmrequest(item['request'])

    @staticmethod
    def responseParser(item):
        return [pmresponse(response) for response in item['response']]

    @staticmethod
    def schemaParser(item):
        schema = dict()
        key = PostmanParser.camelize(pmrequest(item['request']).getPathNormalised())
        for response in item['response']:
            response = pmresponse(response)
            schemaresponse = pmschema(response)
            schema[(key + str(response.getCode()))] = schemaresponse.getSchema()
        return schema

    def getSchemas(self, path=None):
        return self.walker(
            self.pmcollection['item'],
            modifier=lambda item: self.schemaParser(item),
            filter_=lambda item: item.get(path, None) is not None)

    def getItems(self, path=None):
        return self.walker(
            self.pmcollection['item'],
            filter_=lambda item: item.get(path, None) is not None)
