from flask import Flask
from flask_mongoengine import MongoEngine

app = Flask(__name__)
app.config['MONGODB_SETTINGS'] = {
    'db': 'test_app'
}

db = MongoEngine(app)

@app.route('/')
def hello_world():
    return 'Hello, World!'
