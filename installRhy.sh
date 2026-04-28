# 1. Create and activate virtual environment
python3 -m venv ~/ryu_env
source ~/ryu_env/bin/activate

# 2. Install Ryu + compatible eventlet inside the venv
pip install ryu eventlet==0.30.2

# 3. Test
ryu-manager --version
