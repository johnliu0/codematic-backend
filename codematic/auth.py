from flask import Blueprint, request, session
from flask_restful import Api, Resource
from werkzeug.security import check_password_hash, generate_password_hash
import flask_mongoengine as me

from codematic.docs import User

bp = Blueprint('auth', __name__, url_prefix='/auth')
api = Api(bp)

class AuthLogIn(Resource):
    def post(self):
        form_data = request.get_json()
        if 'email' not in form_data or len(form_data['email']) == 0:
            return { 'message': 'No email provided.' }, 400
        if 'password' not in form_data or len(form_data['password']) == 0:
            return { 'message': 'No password provided.' }, 400

        email = form_data['email'] 
        password = form_data['password']
        try:
            user = User.objects.get(email=email)
            password_correct = check_password_hash(user.password_hash, password)
            if not password_correct:
                return { 'message': 'Invalid password.' }, 401
            session['test'] = 'hello'
            return { 'message': 'Successfully logged in.' }, 200
        except me.DoesNotExist:
            return { 'message': f'User with email {email} does not exist.' }, 404

class AuthSignUp(Resource):
    def post(self):
        form_data = request.get_json()
        if 'email' not in form_data or len(form_data['email']) == 0:
            return { 'message': 'No email provided.' }, 400
        if 'password' not in form_data or len(form_data['password']) == 0:
            return { 'message': 'No password provided.' }, 400
        
        email = form_data['email'] 

        # Check if a user with the same email already exists
        try:
            existing_user = User.objects.get(email=email)
            return { 'message': f'User with email {email} already exists' }
        except me.DoesNotExist:
            pass

        password_hash = generate_password_hash(form_data['password'])

        user = User(email=email, password_hash=password_hash)
        user.save()
        
        return { 'message': 'Successfully signed up.' }, 200

api.add_resource(AuthLogIn, '/login')
api.add_resource(AuthSignUp, '/signup')
