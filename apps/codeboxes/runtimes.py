# coding=UTF8
from django.conf import settings

NODEJS_WRAPPER_SOURCE_FORMAT = """
const readline = require("readline");
const vm = require("vm");
const fs = require("fs");

{cached_modules}

const rl = readline.createInterface({{
    input: process.stdin
}});

var _outputSeparator = null;
var _outputResponse = null;

function HttpResponse(status_code, content, content_type, headers) {{
    this.status_code = status_code || 200;
    this.content = content || "";
    this.content_type = content_type || "application/json";
    this.headers = headers || {{}};
}};

HttpResponse.prototype.dump = function() {{
    return JSON.stringify([
        parseInt(this.status_code),
        String(this.content_type),
        String(this.content),
        this.headers,
    ]);
}};

function setResponse(response) {{
    _outputResponse = response;
}};

rl.on("line", (input) => {{
    let context = JSON.parse(input);
    for (var attrname in global) {{ context[attrname] = global[attrname]; }}
    _outputSeparator = context["_OUTPUT_SEPARATOR"]

    const source = fs.readFileSync("{source_dir}/{source_file}.js");
    const script = new vm.Script(source, {{filename: "{source_file}.js"}});

    try {{
        script.runInNewContext(context, {{timeout: context._TIMEOUT * 1000}});
    }} catch (e) {{
        console.error(e);
        if (e.message === "Script execution timed out.") {{
            process.exit(124);
        }}
    }} finally {{
        rl.close();
        process.stdin.destroy();
    }}
}});


process.on("exit", (code) => {{
    if (code == 0 && _outputResponse !== null && _outputResponse instanceof HttpResponse) {{
        console.log(_outputSeparator);
        console.log(_outputResponse.dump());
    }}
}});
"""

NODEJS_WRAPPER_SOURCE = NODEJS_WRAPPER_SOURCE_FORMAT.format(source_dir=settings.CODEBOX_MOUNTED_SOURCE_DIRECTORY,
                                                            source_file=settings.CODEBOX_MOUNTED_SOURCE_ENTRY_POINT,
                                                            cached_modules='global["soap"] = require("soap");')

NODEJS_WRAPPER_SOURCE_LIB = NODEJS_WRAPPER_SOURCE_FORMAT.format(source_dir=settings.CODEBOX_MOUNTED_SOURCE_DIRECTORY,
                                                                source_file=settings.CODEBOX_MOUNTED_SOURCE_ENTRY_POINT,
                                                                cached_modules='require("syncano");')

PYTHON_WRAPPER_SOURCE = """
import json
import six
import signal
import sys
import traceback

# Modules to cache
from syncano import connection, models

_OUTPUT_RESPONSE = None


class HttpResponse:
    def __init__(self, status_code=200, content="", content_type="application/json", headers=None):
        self.status_code = status_code
        self.content = content
        self.content_type = content_type
        self.headers = headers or {{}}

    def _dump(self):
        return json.dumps([int(self.status_code), six.text_type(self.content_type), six.text_type(self.content),
                          self.headers])


def set_response(response):
    global _OUTPUT_RESPONSE
    _OUTPUT_RESPONSE = response


def _handle_timeout(signum, frame):
    traceback.print_stack()
    exit(124)

context = json.loads(sys.stdin.readline().strip())
user_context = context.copy()
user_context.pop("_TIMEOUT")
user_context.update({{"set_response": set_response,
                    "HttpResponse": HttpResponse}})

signal.signal(signal.SIGALRM, _handle_timeout)
signal.setitimer(signal.ITIMER_REAL, context["_TIMEOUT"])

# Exec entry point
try:
    with open("{source_dir}/{source_file}.py") as f:
        code = compile(f.read(), "{source_file}.py", "exec")
        exec(code, user_context)
finally:
    signal.alarm(0)

if _OUTPUT_RESPONSE and isinstance(_OUTPUT_RESPONSE, HttpResponse):
    print(context["_OUTPUT_SEPARATOR"])
    print(_OUTPUT_RESPONSE._dump())
""".format(source_dir=settings.CODEBOX_MOUNTED_SOURCE_DIRECTORY,
           source_file=settings.CODEBOX_MOUNTED_SOURCE_ENTRY_POINT)

RUBY_SOURCE_TEMPLATE = """
require 'json'

ARGS = JSON.parse('{additional_args}')
CONFIG = JSON.parse('{config}')
META = JSON.parse('{meta}')

_OUTPUT_SEPARATOR = '{separator}'

class HttpResponse
  def initialize(status_code = 200, content = '', content_type = 'application/json', headers = {{}})
    @status_code = status_code
    @content = content
    @content_type = content_type
    @headers = headers
  end

  def dump
    JSON.generate([@status_code.to_i, @content_type, @content, @headers])
  end
end

def set_response(response)
  $_output_response = response
end

{original_source}

if $_output_response && $_output_response.is_a?(HttpResponse)
  puts _OUTPUT_SEPARATOR
  puts $_output_response.dump
end
"""

GOLANG_SOURCE_TEMPLATE = """
package main

import "encoding/json"

{original_source}

var (
    ARGS = unmarshallJSON([]byte(`{additional_args}`))
    META = unmarshallJSON([]byte(`{meta}`))
    CONFIG = unmarshallJSON([]byte(`{config}`))
)

func unmarshallJSON(dataRaw []byte) map[string]interface{{}} {{
    var data map[string]interface{{}}
    json.Unmarshal(dataRaw, &data)
    return data
}}
"""

SWIFT_SOURCE_TEMPLATE = """
import Foundation

func deserializeJSON(json: String) throws -> [String: Any] {{
    let jsonData = json.data(using: .utf8)!
    return try JSONSerialization.jsonObject(with: jsonData, options: []) as! [String: Any]
}}

let ARGS = try! deserializeJSON(json: "{additional_args}")
let CONFIG = try! deserializeJSON(json: "{config}")
let META = try! deserializeJSON(json: "{meta}")

var _outputResponse: AnyObject? = nil
var _outputSeparator = "{separator}"

class HttpResponse {{
    var statusCode: Int
    var content: String
    var contentType: String
    var headers: Dictionary<String, String>

    init(statusCode: Int = 200, content: String = "", contentType: String = "application/json",
         headers: Dictionary<String, String> = Dictionary<String, String>()) {{
        self.statusCode = statusCode
        self.content = content
        self.contentType = contentType
        self.headers = headers
    }}
    func _dump() -> String {{
        let arrayData: [Any] = [self.statusCode, self.contentType, self.content, self.headers]
        return try! trySerialize(arrayData)
    }}

    func trySerialize(_ obj: Any) throws -> String {{
        let data = try JSONSerialization.data(withJSONObject: obj, options: [])
        guard let stringData = String(data: data, encoding: .utf8) else {{
            return ""
        }}
        return stringData
    }}
}}

func setResponse(_ obj: HttpResponse){{
    _outputResponse = obj
}}

{original_source}

if let _outputResponse = _outputResponse as? HttpResponse {{
    print(_outputSeparator)
    print(_outputResponse._dump())
}}

"""

PHP_SOURCE_TEMPLATE = """<?php
$ARGS = json_decode('{additional_args}', true);
$META = json_decode('{meta}', true);
$CONFIG = json_decode('{config}', true);

$_output_response = null;
$_output_separator = '{separator}';

class HttpResponse {{

    var $status_code;
    var $content;
    var $content_type;

    function HttpResponse($status_code=200, $content='', $content_type='application/json', $headers=NULL){{
        $this->status_code = $status_code;
        $this->content = $content;
        $this->content_type = $content_type;
        $this->headers = $headers ? $headers : new ArrayObject();
    }}

    function _dump(){{
        return json_encode([
            $this->status_code, $this->content_type, $this->content, $this->headers
        ]);
    }}
}}

function set_response($response){{
    $GLOBALS['_output_response'] = $response;
}}

{original_source}

if ($GLOBALS['_output_response'] && ($GLOBALS['_output_response'] instanceof HttpResponse)) {{
    print $GLOBALS['_output_separator'];
    print $GLOBALS['_output_response']->_dump();
}}
?>
"""

LATEST_NODEJS_RUNTIME = 'nodejs_v6'
LATEST_NODEJS_LIB_RUNTIME = 'nodejs_library_v1.0'
LATEST_PYTHON_RUNTIME = 'python_library_v5.0'

IMAGE = 'quay.io/syncano/script-docker-image:{}'.format(settings.CODEBOX_IMAGE_TAG)
IMAGE_UID = 1000
IMAGE_GID = 1000

RUNTIMES = {
    'nodejs_library_v0.4': {
        'image': IMAGE,
        'wrapper': True,
        'command': "node-lib0.4 -e '\\''{source}'\\''",
        'wrapper_source': NODEJS_WRAPPER_SOURCE_LIB,
        'file_ext': 'js',
        'meta': {
            'name': 'Node.js',
            'version': '6.10.0',
            'library': 'https://github.com/Syncano/syncano-js',
            'library_version': '0.4.x',
            'deprecated': True,
            'image': 'quay.io/syncano/nodejs-codebox',
            'packages': 'https://github.com/Syncano/nodejs-codebox/blob/master/nodejs/files/package.json.v04'
        }
    },
    'nodejs_library_v1.0': {
        'image': IMAGE,
        'wrapper': True,
        'command': "node-lib1.0 -e '\\''{source}'\\''",
        'wrapper_source': NODEJS_WRAPPER_SOURCE_LIB,
        'file_ext': 'js',
        'meta': {
            'name': 'Node.js',
            'version': '6.10.0',
            'library': 'https://github.com/Syncano/syncano-js',
            'library_version': '1.x',
            'deprecated': False,
            'image': 'quay.io/syncano/nodejs-codebox',
            'packages': 'https://github.com/Syncano/nodejs-codebox/blob/master/nodejs/files/package.json.j2'
        }
    },
    'nodejs_v6': {
        'image': IMAGE,
        'wrapper': True,
        'command': "node -e '\\''{source}'\\''",
        'wrapper_source': NODEJS_WRAPPER_SOURCE,
        'file_ext': 'js',
        'meta': {
            'name': 'Node.js',
            'version': '6.10.0',
            'library': None,
            'library_version': None,
            'deprecated': False,
            'image': 'quay.io/syncano/nodejs-codebox',
            'packages': None
        }
    },
    'python_library_v4.2': {
        'image': IMAGE,
        'wrapper': True,
        'command': "python27-lib4.2 -u -c '\\''{source}'\\''",
        'wrapper_source': PYTHON_WRAPPER_SOURCE,
        'file_ext': 'py',
        'meta': {
            'name': 'Python',
            'version': '2.7.x',
            'library': 'https://github.com/Syncano/syncano-python',
            'library_version': '4.2.x',
            'deprecated': True,
            'image': 'quay.io/syncano/python-codebox',
            'packages': 'https://github.com/Syncano/python-codebox/blob/master/python/files/requirements_v42.txt'
        }
    },
    'python_library_v5.0': {
        'image': IMAGE,
        'wrapper': True,
        'command': "python27-lib5.0 -u -c '\\''{source}'\\''",
        'wrapper_source': PYTHON_WRAPPER_SOURCE,
        'file_ext': 'py',
        'meta': {
            'name': 'Python',
            'version': '2.7.x',
            'library': 'https://github.com/Syncano/syncano-python',
            'library_version': '5.x',
            'deprecated': False,
            'image': 'quay.io/syncano/python-codebox',
            'packages': 'https://github.com/Syncano/python-codebox/blob/master/python/files/requirements.txt'
        }
    },
    'python3': {
        'image': IMAGE,
        'wrapper': True,
        'command': "python3-lib5.0 -u -c '\\''{source}'\\''",
        'wrapper_source': PYTHON_WRAPPER_SOURCE,
        'file_ext': 'py',
        'meta': {
            'name': 'Python 3',
            'version': '3.4.x',
            'library': 'https://github.com/Syncano/syncano-python',
            'library_version': '5.x',
            'deprecated': False,
            'image': 'quay.io/syncano/python-codebox',
            'packages': 'https://github.com/Syncano/python-codebox/blob/master/python/files/requirements_python3.txt'
        }
    },
    'ruby': {
        'image': IMAGE,
        'command': 'ruby {source_file}',
        'source_template': RUBY_SOURCE_TEMPLATE,
        'file_ext': 'rb',
        'meta': {
            'name': 'Ruby',
            'version': '2.2.x',
            'library': 'https://github.com/Syncano/syncano-ruby',
            'library_version': '4.0',
            'deprecated': False,
            'image': 'quay.io/syncano/ruby-codebox',
            'packages': 'https://github.com/Syncano/ruby-codebox/blob/master/ruby/files/Gemfile'
        }
    },
    'golang': {
        'image': IMAGE,
        'command': 'go run {source_file}',
        'source_template': GOLANG_SOURCE_TEMPLATE,
        'file_ext': 'go',
        'meta': {
            'name': 'Golang',
            'version': '1.4.x',
            'library': None,
            'library_version': None,
            'deprecated': False,
            'image': 'quay.io/syncano/golang-codebox',
            'packages': None
        }
    },
    'swift': {
        'image': IMAGE,
        'command': 'swift {source_file}',
        'source_template': SWIFT_SOURCE_TEMPLATE,
        'file_ext': 'swift',
        'meta': {
            'name': 'Swift',
            'version': '3.0.x',
            'library': None,
            'library_version': None,
            'deprecated': False,
            'image': 'quay.io/syncano/swift-codebox',
            'packages': None
        }
    },
    'php': {
        'image': IMAGE,
        'command': 'php5 {source_file}',
        'source_template': PHP_SOURCE_TEMPLATE,
        'file_ext': 'php',
        'meta': {
            'name': 'PHP',
            'version': '5.5.x',
            'library': None,
            'library_version': None,
            'deprecated': False,
            'image': 'quay.io/syncano/php-codebox',
            'packages': None
        }
    }
}

# Add aliases
RUNTIMES['nodejs'] = RUNTIMES['nodejs_library_v0.4'].copy()
RUNTIMES['nodejs']['visible'] = False
RUNTIMES['nodejs']['alias'] = 'nodejs_library_v0.4'
RUNTIMES['python'] = RUNTIMES['python_library_v4.2'].copy()
RUNTIMES['python']['visible'] = False
RUNTIMES['python']['alias'] = 'python_library_v4.2'


RUNTIME_NAMES = RUNTIMES.keys()

RUNTIME_CHOICES = list(zip(RUNTIME_NAMES, RUNTIME_NAMES))
RUNTIMES_META = {name: props['meta'] for name, props in RUNTIMES.items() if props.get('visible', True)}
