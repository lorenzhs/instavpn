instavpn
========

### Please note that this project has been abandoned and might or might not work.

Create and set up an instant VPN using DigitalOcean and sshuttle

This is useful in a number of scenarios:
- You're using a network you don't trust and need a secure connection
- You need to tunnel your traffic to a different country to access a website that's unavailable where you live

If you need a VPN every now and then, but not all that often, a dedicated VPS is probably fairly expensive. With instavpn, due to DigitalOcean's amazing pricing, you only pay while you actually use the VPN connection! That's $0.007 per hour for the smallest droplet, which is more than sufficient. If you use it for an hour every day, that's $0.21 a *month*. I probably don't need to say anything else now because you're already sold, right?

## What this is
instavpn provides you with a working VPN connection in a minute. It will create a DigitalOcean droplet in your account, initiate a VPN connection to this newly created droplet as soon as it is ready, and tears it down automatically once you're done. You only pay for the duration you're actually using the VPN.

## What this is not
- A tool to add a VPN to your existing droplet/machine. Just use sshuttle directly.
- A mature piece of software. **Please check if your droplet was really destroyed automatically** and file an issue if it wasn't, but don't tell me I didn't warn you!
- IPv6 ready. Blame DigitalOcean for not supporting it! :(

## Configuration
Before you can get started, you need to create a `settings.py` with your API key. Just copy over `settings.py.dist`, pop in your API key and Client ID – you can find them both in your [DigitalOcean control panel](https://cloud.digitalocean.com/api_access) – and have a look over the default values for the other settings. I'd consider the defaults sane, so you probably won't need to change that much, maybe the region where to create your droplet or the subnet that you want to forward through the VPN.
