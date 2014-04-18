#! /usr/bin/env python3
# encoding: UTF-8

import argparse
import json
import os
import re
import requests
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

import settings

def csv(value):
    return value.split(",")


def parseSlugOrId(name, value):
    if (value.isdigit()):
        return '{name}_id'.format(name=name)
    else:
        return '{name}_slug'.format(name=name)

class API(object):
    # Do an API call (private auxiliary method)
    def _get(self, command, arguments=dict()):
        url = 'https://api.digitalocean.com/{command}'.format(command=command)

        # Add API key and Client ID to arguments
        if not 'api_key' in arguments:
            arguments['api_key'] = settings.API_KEY
        if not 'client_id' in arguments:
            arguments['client_id'] = settings.CLIENT_ID

        # Send the request
        response = requests.get(url=url, params=arguments)
        data = json.loads(response.text)
        if 'status' in data and data['status'] == 'OK':
            return data
        else:
            raise ValueError('API call failed: ' + response.text)

    # Retrieve SSH keys in account
    def getSshKeys(self):
        data = self._get('ssh_keys/')
        keys = []
        if 'ssh_keys' in data:
            for key in data['ssh_keys']:
                keys.append(key['id'])
        return keys

    # Get droplet status by id
    def status(self, droplet_id):
        return self._get('droplets/{id}'.format(id=droplet_id))

    # Create a new droplet
    def createDroplet(self, region, droplet_name, size, image, keys):
        arguments = dict()

        arguments['name'] = droplet_name

        # Is region numerical?
        arguments[parseSlugOrId('region', region)] = region
        arguments[parseSlugOrId('size'  , size  )] = size
        arguments[parseSlugOrId('image' , image )] = image

        # Add SSH keys
        arguments['ssh_key_ids'] = ','.join(keys)

        arguments['private_networking'] = 'false'
        arguments['backups_enabled'] = 'false'

        response = self._get('droplets/new', arguments)
        return response

    # Get full droplet destruction URL for self-destruction mechanism
    def destruct_command(self, id, scrub):
        return 'https://api.digitalocean.com/droplets/{droplet_id}/destroy/?scrub={scrub}&api_key={api_key}&client_id={client_id}'.format(
            droplet_id=id, scrub=scrub, api_key=settings.API_KEY, client_id=settings.CLIENT_ID)

    # Destroy a droplet
    def destroy_droplet(self, id, scrub):
        return self._get('droplets/{id}/destroy/?scrub={scrub}'.format(id=id, scrub=scrub))

# VPN deployment module
class DeploymentModule(object):
    # Find or install sshuttle
    def prepare(self):
        self.sshuttle_path = shutil.which('sshuttle')
        if not self.sshuttle_path:
            print('Could not find sshuttle in path, cloning repository...')
            path = os.path.join(os.getcwd(), 'sshuttle')
            self._clone(path)
            self.sshuttle_path = os.path.join(path, 'sshuttle')

    # clone sshuttle repository
    def _clone(self, path):
        if not os.path.exists(path):
            status = subprocess.call(['git', 'clone', 'git://github.com/apenwarr/sshuttle', path])
            if status != 0:
                raise ValueError('could not clone sshuttle repository')

    # connect to droplet
    def connect(self, remote, proxyDns, subnet, additional, destruction_callback):
        dns = '--dns' if proxyDns else None
        additional_args = shlex.split(additional)

        args = [self.sshuttle_path, dns, '-vr', remote, subnet]
        args += additional_args
        args = list(filter(lambda x: type(x) is str, args))

        # Callback for sshuttle thread
        self.destruction_callback = destruction_callback
        print('Connecting to sshuttle with command', ' '.join(args))

        # Based on http://stackoverflow.com/a/2581943 by
        # StackOverflow User Daniel G
        def asyncRunner(args, parentself):
            parentself.proc = subprocess.Popen(args)
            parentself.proc.communicate()
            returncode = parentself.proc.wait()
            print("sshuttle exited with return code", returncode)
            # sshuttle exited
            if returncode == 1:
                # Tear down droplet
                print('Initiating droplet destruction...')
                parentself.destruction_callback()
                print('Droplet destroyed')

        thread = threading.Thread(target=asyncRunner, args=(args,self))
        # Capture SIGINT and pass it on to sshuttle
        signal.signal(signal.SIGINT, self._signal_handler)
        thread.start()

    def _signal_handler(self, signum, frame):
        # Pass Ctrl+C on to sshuttle
        self.proc.send_signal(signal.SIGINT)


class InstaVPN(object):
    def __init__(self):
        self.api = API()
        self.deployer = DeploymentModule()

    # Create a droplet
    def createMachine(self, args, ssh_keys):
        start_time = time.time()  # for time measurement
        # Initiate droplet creation
        droplet = self.api.createDroplet(args.region, args.droplet_name, args.droplet_size, args.image, ssh_keys)
        droplet_id = droplet["droplet"]["id"]
        print('Droplet creation initiated, id={id}'.format(id=droplet_id))

        # Wait 20 seconds to allow DigitalOcean to create the droplet
        time.sleep(20)

        retries = 0
        state = dict()
        # Periodically check droplet status
        while retries < settings.MAX_RETRIES:
            state = self.api.status(droplet_id)
            status = state["droplet"]["status"]
            if status == "new":
                print("Droplet not yet active, retrying in 5s")
            elif status == "active":
                # Machine is up and running!
                duration = time.time() - start_time
                print("Droplet is up and running! Duration: {time:.0f}s".format(time=duration))
                break
            else:
                print("Droplet has weird status, retrying in 5s:", status, json.dums(state, indent=4))
            time.sleep(5)
            retries += 1

        if not status:
            # Failed to create droplet
            raise ValueError("failed to create droplet :(")

        # Dump droplet state, which can be passed into --debug-state
        print(json.dumps(state))
        return state

    # Set up and connect VPN
    def connect(self, status, subnet, proxyDns, additional_args, scrub):
        droplet = status["droplet"]
        self.droplet_id = droplet["id"]
        self.droplet_ip = droplet["ip_address"]
        self.scrub = scrub

        remote = 'root@' + self.droplet_ip

        self.deployer.prepare()
        self.deployer.connect(remote, subnet, proxyDns, additional_args, self._destroy_droplet)

    # Tear down droplet
    def _destroy_droplet(self):
        self.api.destroy_droplet(self.droplet_id, self.scrub)

    # Set up droplet self-destruction mechanism
    def initiate_self_destruct(self, self_destruct_timeout, scrub):
        apicall = self.api.destruct_command(self.droplet_id, scrub)
        # Hacky shell code for droplet self-destruction. TODO: something nicer.
        destruct_command = """\"\
while true
do
  while true
  do
    if [ \\$(pidof python2) ]
    then
      sleep 10
      echo waiting >> log
    else
      echo not found, starting killing >> log
      break
    fi
  done
  echo waiting for timeout... >> log
  sleep {timeout}
  if [ ! \\$(pidof python2) ]
  then
    echo not found, killing >> log
    break
  fi
done
echo curling >> log
curl \\\"{apicall}\\\" >> log 2>> log
echo done >> log\"""".format(timeout=self_destruct_timeout, apicall=apicall)

        remote = 'root@' + self.droplet_ip
        proc = subprocess.Popen(['ssh', remote, 'nohup', 'bash', '-c', destruct_command])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Instant sshuttle VPN via DigitalOcean')
    # sshuttle arguments
    parser.add_argument('-d', '--dns', dest='proxyDns', action='store_true', default=settings.PROXY_DNS, help='Proxy DNS queries through VPN')
    parser.add_argument('-l', '--subnet', type=str, dest='subnet', default=settings.SUBNET, help='Subnet mask to forward through VPN')
    parser.add_argument('-p', '--params', type=str, dest='additional_args', default=settings.ADDITIONAL_ARGS, help='Additional arguments to pass to sshuttle')
    # Destruction arguments
    parser.add_argument('--no-self-destruct', dest='self_destruct', action='store_false', default=settings.SELF_DESTRUCT, help='Do not self destruct droplet after inactivity period. Droplet will still be destroyed when InstaVPN is quit')
    parser.add_argument('--self-destruct-timeout', type=int, dest='self_destruct_timeout', default=settings.SELF_DESTRUCT_TIMEOUT, help='Timeout for droplet self destruction after connection loss (seconds)')
    parser.add_argument('--scrub', dest='scrub', action='store_true', default=settings.SCRUB, help='Scrub droplet after destruction')
    # Droplet arguments
    parser.add_argument('-r', '--region', type=str, dest='region', default=settings.REGION, help='Region to create the droplet in (slug or id)')
    parser.add_argument('-n', '--name', type=str, dest='droplet_name', default=settings.NAME, help='Name of the droplet')
    parser.add_argument('-s', '--size', type=str, dest='droplet_size', default=settings.SIZE, help='Droplet size (slug or id)')
    parser.add_argument('-i', '--image', type=str, dest='image', default=settings.IMAGE, help='Droplet image (slug or id)')
    parser.add_argument('--all-keys', dest='all_keys', default=False, help='Retrieve and add all keys in your account to the droplet')
    parser.add_argument('-k', '--keys', type=csv, dest='ssh_keys', default=settings.SSH_KEY_IDS, help='SSH key IDs to add to your droplet')
    # Debug
    parser.add_argument('--debug-state', type=str, dest='debugstate', help='Load droplet state from JSON string instead of creating new droplet')
    args = parser.parse_args()

    # Verify droplet name validity
    name_regex = re.compile('^[a-zA-Z0-9\.-]+$')
    if not name_regex.match(args.droplet_name):
        print("Only valid hostname characters are allowed. (a-z, A-Z, 0-9, . and -)")
        sys.exit(1)

    # Set up droplet or load state
    vpn = InstaVPN()
    if args.debugstate:
        status = json.loads(args.debugstate)
    else:
        ssh_keys = args.ssh_keys
        if args.all_keys:
            ssh_keys = getSshKeys()

        status = vpn.createMachine(args, ssh_keys)

    # Connect to droplet
    vpn.connect(status, args.proxyDns, args.subnet, args.additional_args, args.scrub)
    if (args.self_destruct):
        print("Setting up self-destruct mechanism on droplet...")
        vpn.initiate_self_destruct(args.self_destruct_timeout, args.scrub)
