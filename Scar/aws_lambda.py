#! /usr/bin/python

# SCAR - Serverless Container-aware ARchitectures
# Copyright (C) GRyCAP - I3M - UPV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import configparser
from enum import Enum
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile

import Scar.scar_utils as scar_utils

config_file_folder = os.path.expanduser("~") + "/.scar"
config_file_name = "scar.cfg"
config_file_path = config_file_folder + '/' + config_file_name


class OutputType(Enum):
    VERBOSE = 1
    JSON = 2
    TABLE = 3
    PLAIN_TEXT = 4


class AWSLambda(object):

    def __init__(self, aws_client):
        # Parameters needed to create the function in AWS
        self.asynchronous_call = False
        self.aws_client = aws_client
        self.code = None
        self.container_arguments = None
        self.delete_all = False
        self.description = "Automatically generated lambda function"    
        self.environment = { 'Variables' : {} }
        self.event = { "Records" : [
                    { "eventSource" : "aws:s3",
                      "s3" : {
                          "bucket" : {
                              "name" : ""},
                          "object" : {
                              "key" : "" }
                        }
                    }
                ]}
        self.event_source = None
        self.extra_payload = None
        self.function_arn = None
        self.handler = None
        self.image_id = None
        self.invocation_type = "RequestResponse"
        self.log_group_name = None
        self.log_retention_policy_in_days = 30
        self.log_stream_name = None
        self.log_type = "Tail"
        self.memory = 512
        self.name = None
        self.output = OutputType.PLAIN_TEXT
        self.payload = "{}"
        self.recursive = False        
        self.region = 'us-east-1'
        self.request_id = None
        self.role = None
        self.runtime = "python3.6"
        self.scar_call = None
        self.script = None
        self.tags = {}
        self.time = 300
        self.timeout_threshold = 10
        self.udocker_dir = "/tmp/home/.udocker"
        self.udocker_tarball = "/var/task/udocker-1.1.0-RC2.tar.gz"
        self.zip_file_path = os.path.join(tempfile.gettempdir(), 'function.zip')

    def set_log_stream_name(self, stream_name):
        self.log_stream_name = stream_name
        
    def set_request_id(self, request_id):
        self.request_id = request_id
        
    def is_asynchronous(self):
        return self.asynchronous_call

    def has_event_source(self):
        return self.event_source is not None
    
    def delete_all(self):
        return self.delete_all
        
    def has_verbose_output(self):
        return self.verbose_output
    
    def has_json_output(self):
        return self.json_output
        
    def set_payload(self, payload):
        self.payload = json.dumps(payload)
        
    def set_cont_args(self, container_arguments):
        self.container_arguments = container_arguments

    def set_async(self, asynchronous_call):
        if asynchronous_call:
            self.set_asynchronous_call_parameters()
        else:
            self.set_request_response_call_parameters()

    def set_func(self, scar_call):
        self.scar_call = scar_call.__name__

    def set_asynchronous_call_parameters(self):
        self.asynchronous_call = True
        self.invocation_type = "Event"
        self.log_type = "None"

    def set_request_response_call_parameters(self):
        self.asynchronous_call = False
        self.invocation_type = "RequestResponse"
        self.log_type = "Tail"

    def set_name(self, name):
        if not is_valid_name(name):
            print("'%s' is an invalid lambda function name." % name)
            logging.error("'%s' is an invalid lambda function name." % name)
            scar_utils.finish_failed_execution()            
        self.name = name        
    
    def set_image_id(self, image_id):
        self.image_id = image_id
        if not hasattr(self, 'name') or self.name == "":
            self.set_name(self.aws_client.create_function_name(image_id))
    
    def set_memory(self, memory):
        self.memory = self.aws_client.check_memory(memory)        

    def set_time(self, time):
        self.time = self.aws_client.check_time(time)
        
    def set_timeout_threshold(self, timeout_threshold):
        self.timeout_threshold = timeout_threshold
        
    def set_json(self, json):
        if json:
            self.output = OutputType.JSON
        
    def set_verbose(self, verbose):
        if verbose:
            self.output = OutputType.VERBOSE
        
    def set_script(self, script):
        self.script = script
        
    def set_event_source(self, event_source):
        self.event_source = event_source
        self.event['Records'][0]['s3']['bucket']['name'] = event_source
        
    def set_event_source_file_name(self, file_name):
        self.event['Records'][0]['s3']['object']['key'] = file_name        
        
    def set_lambda_role(self, lambda_role):
        self.lambda_role = lambda_role
        
    def set_recursive(self, recursive):
        self.recursive = recursive
        
    def set_preheat(self, preheat):
        self.preheat = preheat
        
    def set_extra_payload(self, extra_payload):
        self.extra_payload = extra_payload

    def set_code(self):
        self.code = {"ZipFile": self.create_zip_file()}
        
    def set_evironment_variable(self, key, value):
        self.environment['Variables'][key] = value
               
    def set_required_environment_variables(self):
        self.set_evironment_variable('UDOCKER_DIR', self.udocker_dir)
        self.set_evironment_variable('UDOCKER_TARBALL', self.udocker_tarball)
        self.set_evironment_variable('TIMEOUT_THRESHOLD', str(self.timeout_threshold))
        self.set_evironment_variable('RECURSIVE', str(self.recursive))
        self.set_evironment_variable('IMAGE_ID', self.image_id)        

    def set_environment_variables(self, variables):
        for env_var in variables:
            parsed_env_var = env_var.split("=")
            # Add an specific prefix to be able to find the variables defined by the user
            key = 'CONT_VAR_' + parsed_env_var[0]
            self.set_evironment_variable(key, parsed_env_var[1])

    def set_tags(self):
        self.tags['createdby'] = 'scar'
        self.tags['owner'] = self.aws_client.get_user_name_or_id()

    def set_all(self, value):
        self.delete_all = value
          
    def validate_lambda_configuration(self):
        if not self.role or self.role == "":
            logging.error("Please, specify first a lambda role in the '%s/%s' file." % (config_file_folder, config_file_name))
            scar_utils.finish_failed_execution()

    def get_argument_value(self, args, attr):
        if attr in args.__dict__.keys():
            return args.__dict__[attr]

    def update_function_attributes(self, args):
        if self.get_argument_value(args, 'memory'):
            self.aws_client.update_function_memory(self.name, self.memory)
        if self.get_argument_value(args, 'time'):
            self.aws_client.update_function_timeout(self.name, self.time)
        if self.get_argument_value(args, 'env'):
            self.aws_client.update_function_env_variables(self.name, self.environment)        

    def check_function_name(self):
        if self.name:
            if self.scar_call == 'init':
                self.aws_client.check_function_name_exists(self.name)
            elif (self.scar_call == 'rm') or (self.scar_call == 'run'):
                self.aws_client.check_function_name_not_exists(self.name)

    def set_attributes(self, args):
        # First set command line attributes
        for attr in args.__dict__.keys():
            value = self.get_argument_value(args, attr)
            try:
                if value is not None:
                    method_name = 'set_' + attr
                    method = getattr(self, method_name)
                    method(value)
            except Exception as ex:
                logging.error(ex)
        
        self.check_function_name()
        self.set_required_environment_variables()
        if self.name:
            self.handler = self.name + ".lambda_handler"
            self.log_group_name = '/aws/lambda/' + self.name
        if self.scar_call == 'init':
            self.set_tags()
            self.set_code()
        elif self.scar_call == 'run':
            self.update_function_attributes(args)
            if self.get_argument_value(args, 'script'):
                self.set_payload(self.create_payload("script", self.get_escaped_script()))
            if self.get_argument_value(args, 'cont_args'):
                self.set_payload(self.create_payload("cmd_args", self.get_parsed_cont_args()))             

    def create_payload(self, key, value):
        return { key : value }

    def get_escaped_script(self):
        return scar_utils.escape_string(self.script.read())

    def get_parsed_cont_args(self):
        return scar_utils.escape_list(self.container_arguments)

    def get_default_json_config(self):
        return { 'lambda_description' : self.description,
                 'lambda_memory' : self.memory,
                 'lambda_time' : self.time,
                 'lambda_region' : self.region,
                 'lambda_role' : '',
                 'lambda_timeout_threshold' : self.timeout_threshold }

    def check_config_file(self):
        config_parser = configparser.ConfigParser()
        # Check if the config file exists
        if os.path.isfile(config_file_path):
            config_parser.read(config_file_path)
            self.parse_config_file_values(config_parser)
        else:
            # Create scar config dir
            os.makedirs(config_file_folder, exist_ok=True)
            self.create_default_config_file(config_parser, config_file_path)
        self.validate_lambda_configuration()
    
    def create_default_config_file(self, config_parser, config_file_path):
        config_parser['scar'] = self.get_default_json_config()
        with open(config_file_path, "w") as config_file:
            config_parser.write(config_file)
        logging.warning("Config file '%s' created.\nPlease, set first a valid lambda role to be used." % config_file_path)
        scar_utils.finish_successful_execution()
    
    def parse_config_file_values(self, config_parser):
        scar_config = config_parser['scar']
        self.role = scar_config.get('lambda_role', self.role)
        self.region = scar_config.get('lambda_region', self.region)
        self.memory = scar_config.getint('lambda_memory', self.memory)
        self.time = scar_config.getint('lambda_time', self.time)
        self.description = scar_config.get('lambda_description', self.description)
        self.timeout_threshold = scar_config.getint('lambda_timeout_threshold', self.timeout_threshold)
        
    def get_scar_abs_path(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    def create_zip_file(self):
        scar_dir = self.get_scar_abs_path()
        # Set generic lambda function name
        function_name = self.name + '.py'
        # Copy file to avoid messing with the repo files
        # We have to rename the file because the function name affects the handler name
        shutil.copy(scar_dir + '/lambda/scarsupervisor.py', function_name)
        # Zip the function file
        with zipfile.ZipFile(self.zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # AWSLambda function code
            zf.write(function_name)
            os.remove(function_name)
            # Udocker script code
            zf.write(scar_dir + '/lambda/udocker', 'udocker')
            # Udocker libs
            zf.write(scar_dir + '/lambda/udocker-1.1.0-RC2.tar.gz', 'udocker-1.1.0-RC2.tar.gz')
    
            if self.script:
                zf.write(self.script, 'init_script.sh')
                self.set_evironment_variable('INIT_SCRIPT_PATH', "/var/task/init_script.sh")
                
        if self.extra_payload:
            self.zip_folder(self.zip_file_path, self.extra_payload)
            self.set_evironment_variable('EXTRA_PAYLOAD', "/var/task/extra/")
    
        # Return the zip as an array of bytes
        with open(self.zip_file_path, 'rb') as f:
            return f.read()
    
    def zip_folder(self, zipPath, target_dir):            
        with zipfile.ZipFile(zipPath, 'a', zipfile.ZIP_DEFLATED) as zf:
            rootlen = len(target_dir) + 1
            for base, _, files in os.walk(target_dir):
                for file in files:
                    fn = os.path.join(base, file)
                    zf.write(fn, 'extra/' + fn[rootlen:])

                    
def is_valid_name(function_name):
    if function_name:
        # aws_name_regex = "((arn:(aws|aws-us-gov):lambda:)?([a-z]{2}(-gov)?-[a-z]+-\d{1}:)?(\d{12}:)?(function:)?([a-zA-Z0-9-]+)(:($LATEST|[a-zA-Z0-9-]+))?)"
        aws_name_regex = "(arn:(aws[a-zA-Z-]*)?:lambda:)?([a-z]{2}(-gov)?-[a-z]+-\d{1}:)?(\d{12}:)?(function:)?([a-zA-Z0-9-_]+)(:(\$LATEST|[a-zA-Z0-9-_]+))?"           
        pattern = re.compile(aws_name_regex)
        func_name = pattern.match(function_name)
        return func_name and (func_name.group() == function_name)
    return False                    
