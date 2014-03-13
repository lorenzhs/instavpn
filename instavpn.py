#! /usr/bin/env python3
# encoding: UTF-8

import argparse
import json
import requests
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

    def getRegions(self):
        return self._get('regions/')

    def getSshKeys(self):
        data = self._get('ssh_keys/')
        keys = []
        if 'ssh_keys' in data:
            for key in data['ssh_keys']:
                keys.append(key['id'])
        return keys

    def status(self, droplet_id):
        return self._get('droplets/{id}'.format(id=droplet_id))


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

        print arguments

        response = self._get('droplets/new', arguments)
        return response

class InstaVPN(object):
    def __init__(self):
        self.api = API()

    def createMachine(self, args, ssh_keys):
        droplet = self.api.createDroplet(args.region, args.droplet_name, args.droplet_size, args.image, ssh_keys)
        droplet_id = droplet["droplet"]["id"]
        print(droplet, droplet_id)

        # Wait 20 seconds to allow DigitalOcean to create the droplet
        time.sleep(20)

        retries = 0
        state = dict()
        while retries < settings.MAX_RETRIES:
            state = self.api.status(droplet_id)
            status = state["droplet"]["status"]
            if status == "new":
                print("Droplet not yet active:", status, json.dumps(state, indent=4))
                time.sleep(5)
                retries += 1
            elif status == "active":
                # Machine is up and running!
                print("Droplet is up and running!")
                break
            else:
                print("Droplet has weird status:", status, json.dums(state, indent=4))
                time.sleep(5)
                retries += 1

        if not status:
            # Failed to create droplet
            raise ValueError("failed to create droplet :(")

        print(json.dumps(state, indent=4))
        ip = state["droplet"]["ip"]
        return state

    def prepareMachine(self, status):
        droplet = status["droplet"]
        droplet_id = droplet["id"]
        droplet_ip = droplet["ip_address"]

        return status



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Instant OpenVPN via DigitalOcean')
    parser.add_argument('-r', '--region', type=str, dest='region', default=settings.REGION, help='Region to create the droplet in (slug or id)')
    parser.add_argument('-n', '--name', type=str, dest='droplet_name', default=settings.NAME, help='Name of the droplet')
    parser.add_argument('-s', '--size', type=str, dest='droplet_size', default=settings.SIZE, help='Droplet size (slug or id)')
    parser.add_argument('-i', '--image', type=str, dest='image', default=settings.IMAGE, help='Droplet image (slug or id)')
    parser.add_argument('--all-keys', dest='all_keys', default=False, help='Retrieve and add all keys in your account to the droplet')
    parser.add_argument('-k', '--keys', type=csv, dest='ssh_keys', default=settings.SSH_KEY_IDS, help='SSH key IDs to add to your droplet')
    parser.add_argument('--debug-state', type=str, dest='debugstate', help='Load droplet state from JSON string')
    args = parser.parse_args()


    vpn = InstaVPN()
    if args.debugstate:
        status = json.loads(args.debugstate)
    else:
        ssh_keys = args.ssh_keys
        if args.all_keys:
            ssh_keys = getSshKeys()

        status = vpn.createMachine(args, ssh_keys)
    status = vpn.prepareMachine(status)
    print(status)
