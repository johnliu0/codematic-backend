import os
import datetime
import re
import uuid
import asyncio
import shutil
from pathlib import Path
from typing import List

import docker
from flask import Blueprint, request, json
from flask_restful import Api, Resource
from flask_socketio import emit

from .socket import socketio

bp = Blueprint('executor', __name__, url_prefix='/executor')
api = Api(bp)

class Executor:
    # List of supported languages and versions
    SUPPORTED_LANGS = ['c++17']
    # Max time allowed for a sbumission to run a test case in seconds
    TEST_CASE_TIME_LIMIT = 5
    # Docker container memory limit in mb
    CONTAINER_MEMORY_LIMIT = 50
    # Docker container max CPU allotment (% of 1 CPU)
    CONTAINER_CPU_LIMIT = 0.05
    # Number of containers to run in parallel for one submission
    CONTAINERS_PER_SUBMISSION = 3

    """Socket status message return types"""
    BUILDING_DOCKER_IMAGE = 0
    DOCKER_IMAGE_BUILT = 1
    STARTING_DOCKER_CONTAINER = 2
    DOCKER_CONTAINER_STARTED = 3
    RUNNING_TEST_CASE = 4
    FINISHED_TEST_CASE = 5
    CLEANING_UP = 6
    FINISHED = 7

    """Test case statuses"""
    TEST_CASE_PASSED = 0
    TEST_CASE_FAILED = 1
    TEST_CASE_TIMED_OUT = 2
    
    async def build_and_run_submission(self,
        source_codes: List[str], source_code_filenames: List[str], test_case_inputs: List[str], test_case_outputs: List[str],
        temp_dir: str, lang: str, entry_point: str) -> None:
        """
        Builds the program from source and runs the code against all the test case pairs of inputs and outputs.

        Args:
            source_codes: List of source codes, each string being its own file.
            source_code_filenames: List of the names of the file that each source code will be put in
            test_case_inputs: List of test case inputs, each string being its own file.
            test_case_outputs: List of test case outputs, each string being its own file.
            temp_dir: Directory where a temporary folder will be created for building the program.
            lang: The programming language used. Must be one of Executor.SUPPORTED_LANGS.
            entry_point: If the programming language does not require compilation, then the entry point
                specifies the name of the file that should be run. If the programming language requires compilation,
                then the entry point specifies the name of the output executable after compilation.
        """
        submission_time = datetime.datetime.now()

        # Generate a unique id for this submission
        # This will be used to name the Docker image, the Docker containers, and the temporary build directories
        unique_id = str(uuid.uuid1())

        # Create a temporary build directory where the Docker image will be created from
        build_dir = os.path.join(temp_dir, unique_id)

        submission_path = os.path.join(build_dir, 'main.c')
        test_case_path = os.path.join(build_dir, 'testcase0.in')
        try:
            # Make the build directory
            os.makedirs(build_dir)

            # Write each source code to its own file
            for source_code, filename in zip(source_codes, source_code_filenames):
                file_path = os.path.join(build_dir, filename)
                with open(file_path, 'w') as f:
                    f.write(source_code)
            
            # Write each test case input to its own file
            for idx, input_text in enumerate(test_case_inputs):
                file_path = os.path.join(build_dir, f'test_case_{idx}.in')
                with open(file_path, 'w') as f:
                    f.write(input_text)

            dockerfile_path = os.path.join(build_dir, 'Dockerfile')
            compilation_args = ' '.join(source_code_filenames)
            s = """
            FROM gcc:4.9
            COPY . /usr/src/myapp
            WORKDIR /usr/src/myapp
            RUN g++ -o """ + f'{entry_point} {compilation_args}'

            print('Loading Docker client')
            docker_client = docker.from_env()
            dockerfile = open(dockerfile_path, 'w')
            dockerfile.write(s)
            dockerfile.close()

            socketio.emit('status', json.dumps({ 'type': self.BUILDING_DOCKER_IMAGE, 'message': 'Building Docker image', 'data': {} }))
            print('Building Docker image')
            docker_image, _ = docker_client.images.build(
                rm=True, path=build_dir, tag='test1')
            print('Docker image built successfully')
            socketio.emit('status', json.dumps({ 'type': self.DOCKER_IMAGE_BUILT, 'message': 'Docker image built successfully', 'data': {} }))

            extra_args = f'--memory="{self.CONTAINER_MEMORY_LIMIT}M" --cpus={self.CONTAINER_CPU_LIMIT}'
            # process = await asyncio.create_subprocess_shell(
            #    f'docker run -i --rm --name test_container {extra_args} {docker_image.id}',
            #    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

            print('Starting Docker container')
            socketio.emit('status', json.dumps({ 'type': self.STARTING_DOCKER_CONTAINER, 'message': 'Starting Docker container', 'data': {} }))
            container = docker_client.containers.run(docker_image.id,
                remove=True, # --rm, removes the container after it finishes running
                tty=True, # -t, TTY
                stdin_open=True, # -i, interactive
                name='test_container', # --name, specifies the name of the container
                detach=True, # -d, place the container into the background after it is created
                mem_limit=f'{self.CONTAINER_MEMORY_LIMIT}M' # --mem-limit, maximum amount of memory that the container can use
            )

            print('Docker container started')
            socketio.emit('status', json.dumps({ 'type': self.DOCKER_CONTAINER_STARTED, 'message': 'Docker container started', 'data': {} }))

            
            for idx, expected_output in enumerate(test_case_outputs):
                print(f'Running test case {idx}')
                socketio.emit('status', json.dumps({ 'type': self.RUNNING_TEST_CASE, 'message': f'Running test case {idx}', 'data': { 'testCase': idx } }))
                exit_code, container_output = container.exec_run(f'sh -c "./{entry_point} < test_case_{idx}.in"')
                container_output = container_output.decode('utf-8')
                status = self.TEST_CASE_PASSED
                if container_output != expected_output:
                    status = self.TEST_CASE_FAILED
                print(f'Finished test case {idx}, Status: {status}')
                #print(exit_code)
                #print(container_output)
                message = f'Test case {idx} ' + ('passed' if status == self.TEST_CASE_PASSED else 'failed')
                socketio.emit('status', json.dumps({ 'type': self.FINISHED_TEST_CASE, 'message': message, 'data': { 'testCase': idx, 'status': status } }))

            print('Cleaning up')
            socketio.emit('status', json.dumps({ 'type': self.CLEANING_UP, 'message': 'Cleaning up', 'data': {} }))

            container.stop()
            docker_client.images.remove(docker_image.id, force=True)

            print('Finished')
            socketio.emit('status', json.dumps({ 'type': self.FINISHED, 'message': 'Finished', 'data': {} }))




            #completed_proc = subprocess.run(
             #   f'docker run -i --rm --name test_container {extra_args} {docker_image.id} < {test_case_path}',
             #   shell=True, capture_output=True)

            #print(completed_proc)

            # print('Waiting for Docker container to finish')
            # prog_out, prog_err = await asyncio.wait_for(process.communicate(), timeout=self.TEST_CASE_TIME_LIMIT)
            # print('# PROG_OUT')
            #print(completed_proc.stdout)
            # print('# PROG_ERR')
            #print(completed_proc.stderr)

        except Exception as e:
            #shutil.rmtree(build_dir, ignore_errors=True)
            print(f'Failed to build and run submission.')
            print(e)
            raise e
        finally:
            pass
            # Clean up build directory
            #shutil.rmtree(build_dir, ignore_errors=True)









class ExecutorEndpoint(Resource):
    def get(self):
        return { 'message': 'Hello' }
    def post(self):
        form_data = request.get_json()
        if 'sourceCodes' not in form_data:
            return { 'message': 'No source codes provided.' }, 400
        if 'sourceCodeFilenames' not in form_data:
            return { 'message': 'No source code filenames provided.' }, 400
        if 'testCaseInputs' not in form_data:
            return { 'message': 'No test case inputs provided.' }, 400
        if 'testCaseOutputs' not in form_data:
            return { 'message': 'No test case outputs provided.' }, 400

        source_codes = form_data['sourceCodes'] 
        source_code_filenames = form_data['sourceCodeFilenames']
        test_case_inputs = form_data['testCaseInputs']
        test_case_outputs = form_data['testCaseOutputs']

        print(source_codes)
        print(source_code_filenames)
        print(test_case_inputs)
        print(test_case_outputs)

        if len(source_codes) != len(source_code_filenames):
            return { 'message': 'Number of source codes differs from number of source code filenames' }, 400
        if len(test_case_inputs) != len(test_case_outputs):
            return { 'message': 'Number of test case inputs differs from number of test case outputs' }, 400

        # Unescape escaped characters such as \n in the source code and test case inputs and outputs
        for i in range(len(source_codes)):
            source_codes[i] = source_codes[i].encode('utf-8').decode('unicode_escape')
        for i in range(len(test_case_inputs)):
            test_case_inputs[i] = test_case_inputs[i].encode('utf-8').decode('unicode_escape')
            test_case_outputs[i] = test_case_outputs[i].encode('utf-8').decode('unicode_escape')
        
        # Ensure that all source code filenames contain only alphanumeric characters and periods
        for filename in source_code_filenames:
            for c in filename:
                if not re.match('[a-zA-Z0.9\.]', c):
                    return { 'message': f'Invalid filename: {filename}'}
        
        # Set the temporary directory where all the code and build files will go
        temp_dir = os.path.join(Path.home(), 'codematic', 'temp')

        try:
            executor = Executor()
            run_result = asyncio.run(executor.build_and_run_submission(
                source_codes, source_code_filenames, test_case_inputs, test_case_outputs, temp_dir, 'c++17', 'main'))
            print(run_result)
        except:
            print('Submission did not successfully complete.')
            return { 'message': 'Submission failed.' }, 400
        return { 'message': 'Success!' }

@socketio.on('message')
def handle_message(data):
    print('Received message:', data)

@socketio.on('connect')
def handle_connection(data):
    print('A user connected.')

@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected')

api.add_resource(ExecutorEndpoint, '/run')