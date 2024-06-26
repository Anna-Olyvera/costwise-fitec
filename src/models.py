from datetime import datetime, timedelta
import enum
import secrets

import jwt
from flask import url_for, current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Updateable:
    def update(self, data):
        for attr, value in data.items():
            setattr(self, attr, value)


user_project = db.Table('user_project',
                        db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                        db.Column('project_id', db.Integer, db.ForeignKey('project.id'), primary_key=True))


class Token(db.Model):
    __tablename__ = "token"
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(64))
    access_expiration = db.Column(db.DateTime)
    refresh_token = db.Column(db.String(64))
    refresh_expiration = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    user = db.relationship('User', backref='tokens')

    @property
    def access_token_jwt(self):
        return jwt.encode({'token': self.access_token},
                          current_app.config['SECRET_KEY'],
                          algorithm='HS256')

    def generate(self):
        self.access_token = secrets.token_urlsafe()
        self.access_expiration = datetime.utcnow() + timedelta(minutes=current_app.config['ACCESS_TOKEN_MINUTES'])
        self.refresh_token = secrets.token_urlsafe()
        self.refresh_expiration = datetime.utcnow() + timedelta(days=current_app.config['REFRESH_TOKEN_DAYS'])

    def expire(self, delay=5):
        self.access_expiration = datetime.utcnow() + timedelta(seconds=delay)
        self.refresh_expiration = datetime.utcnow() + timedelta(seconds=delay)

    @staticmethod
    def clean():
        """Remove any tokens that have been expired for more than a day."""
        yesterday = datetime.utcnow() - timedelta(days=1)
        db.session.query(Token).where(Token.refresh_expiration < yesterday).delete()
        db.session.commit()

    @staticmethod
    def from_jwt(access_token_jwt):
        access_token = None
        try:
            access_token = jwt.decode(access_token_jwt,
                                      current_app.config['SECRET_KEY'],
                                      algorithms=['HS256'])['token']
            return db.session.scalar(db.session.query(Token).filter_by(access_token=access_token))
        except jwt.PyJWTError:
            pass


class User(Updateable, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255))

    @property
    def url(self):
        return url_for('users.get_user', id=self.id)

    def __repr__(self):
        return '<User {}-{}>'.format(self.id, self.username)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_auth_token(self):
        token = Token(user=self)
        token.generate()
        return token

    @staticmethod
    def verify_access_token(access_token_jwt):
        token = Token.from_jwt(access_token_jwt)
        if token:
            if token.access_expiration > datetime.utcnow():
                return token.user

    @staticmethod
    def verify_refresh_token(refresh_token, access_token_jwt):
        token = Token.from_jwt(access_token_jwt)
        if token and token.refresh_token == refresh_token:
            if token.refresh_expiration > datetime.utcnow():
                return token

            # someone tried to refresh with an expired token
            # revoke all tokens from this user as a precaution
            token.user.revoke_all()
            db.session.commit()

    def revoke_all(self):
        db.session.query(Token).where(Token.user == self).delete()
        db.session.commit()


class Project(db.Model):
    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    name_project = db.Column(db.String(255), nullable=False)
    description_project = db.Column(db.String(500))
    deadline = db.Column(db.Date)
    budget = db.Column(db.Integer)
    total_cost_software = db.Column(db.Integer)
    total_cost_hardware = db.Column(db.Integer)
    total_cost_other = db.Column(db.Integer)
    total_time_tasks = db.Column(db.DateTime)

    members = db.relationship('Member', backref='project')
    tasks = db.relationship('Task', backref='project')
    products = db.relationship('Product', backref='project')
    users = db.relationship('User', secondary=user_project, backref='projects')


member_task = db.Table('member_task',
                       db.Column('member_id', db.Integer, db.ForeignKey('member.id'), primary_key=True),
                       db.Column('task_id', db.Integer, db.ForeignKey('task.id'), primary_key=True))


class Member(db.Model):
    __tablename__ = "member"

    id = db.Column(db.Integer, primary_key=True)
    name_member = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(255), nullable=False)
    salary = db.Column(db.Integer)

    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)


class Task(db.Model):
    __tablename__ = "task"

    id = db.Column(db.Integer, primary_key=True)
    name_task = db.Column(db.String(255), nullable=False)
    description_task = db.Column(db.String(500))
    deadline = db.Column(db.Date)

    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    members = db.relationship('Member', secondary=member_task, backref='tasks')


class ProductType(enum.Enum):
    HARDWARE = 'HARDWARE'
    SOFTWARE = 'SOFTWARE'
    OTHER = 'OTHER'


class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    name_product = db.Column(db.String(255), nullable=False)
    cost = db.Column(db.Integer, nullable=False)
    license = db.Column(db.Boolean, nullable=False)
    type = db.Column(db.Enum(ProductType), nullable=False)
    amount = db.Column(db.Integer)

    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
