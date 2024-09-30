#!/bin/bash

# Run the main_challenge_manipulation_phase2.py script
python src/main_challenge_manipulation_phase2.py \
    --num_envs 4 \
    --num_steps 100000 \
    --save_every 10000 \
    --batch_size 64

# Check if the script executed successfully
if [ $? -eq 0 ]; then
    echo "Script executed successfully"
else
    echo "Script execution failed"
fi