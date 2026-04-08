#!/bin/bash

sudo ip link set dev ens19 xdp off
sudo python3 gRPC_o_final.py
