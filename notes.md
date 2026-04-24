#install specific version of python using pyenv
pyenv install 3.11.9

#select version
pyenv local 3.11.9

#verfiy the version
pyenv exec python -V
#create virtual environment
pyenv exec python -m venv .venv

## venv is the moodule and .venv is the name of the virtual environment and . because .files are hidden

#to activate the virtual environment depends on the operating system

source .venv/bin/activate #for linux and macos
.venv\Scripts\activate #for windows cmd
.venv\Scripts/Activate.ps1 #for windows powershell

#install dependencies
pip install -r requirements.txt
#run the fastapi application using uvicorn and ensure app restarts on code changes
uvicorn blogapi.main:app --reload
#warn you about the issues in your code and suggest fixes and it can sort imports and format your code according to the best practices but we need to add settings in order to use it for formatting, linting and sorting imports
ruff check . --fix