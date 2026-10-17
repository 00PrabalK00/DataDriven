#!/usr/bin/env bash
# Keep an SSH tunnel to the remote drop server open (reconnects if it drops). Port 7777 -> remote 127.0.0.1:7777.
while :; do
  ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 7777:127.0.0.1:7777 chute-vast
  sleep 5
done
