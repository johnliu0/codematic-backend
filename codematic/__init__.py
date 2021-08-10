import os
from flask import Flask
from flask_cors import CORS
from flask_mongoengine import MongoEngine

def create_app(test_config=None):
    # Create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev_secret_key',   
    )

    app.config['MONGODB_SETTINGS'] = {
        'db': 'test_app'
    }

    db = MongoEngine(app)
    """
    if test_config == None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)
    """

    from . import auth, executor
    from .socket import socketio
    app.register_blueprint(auth.bp)
    app.register_blueprint(executor.bp)

    CORS(app)
    socketio.init_app(app)
    return app
