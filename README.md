instavpn
========

Create and set up an instant VPN using DigitalOcean and sshuttle

This is a bit of a work in progress.

## What this is
instavpn provides you with a working VPN connection in a minute. It will create a DigitalOcean droplet in your account, initiate a VPN connection to this newly created droplet as soon as it is ready, and tears it down automatically once you're done. You only pay for the duration you actually use the VPN. Typically, that should be less than $1 a month (if you're going to be using that VPN a lot over a long time, renting a tiny VPS might be cheaper and this might not be the right tool for you).

## What this is not
A tool to add a VPN to your existing droplet/machine. Just use sshuttle directly.

## TODO
- destroy droplet immediately when manually exiting the VPN (not just after 20mins of inactivity)
- more robust droplet self-destruction mechanism. Waiting until no `python2` process has existed for 20 minutes is rather hacky
