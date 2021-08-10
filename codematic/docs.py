import mongoengine as me

class TestCase(me.EmbeddedDocument):
    input = me.StringField(required=True)
    output = me.StringField(required=True)

class Program(me.EmbeddedDocument):
    src_code = me.StringField(required=True)
    test_cases = me.ListField(me.EmbeddedDocumentField(TestCase))

class User(me.Document):
    email = me.StringField(required=True)
    password_hash = me.StringField(required=True)
    programs = me.ListField(me.EmbeddedDocumentField(Program))

