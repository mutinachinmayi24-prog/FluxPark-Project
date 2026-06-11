from flask import Flask
from models import db

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SECRET_KEY"] = "fluxpark-secret"

db.init_app(app)

with app.app_context():
    db.create_all()

@app.route("/")
def home():
    return """
    <h1>FluxPark</h1>
    <h3>Database Connected Successfully</h3>
    """

if __name__ == "__main__":
    app.run(debug=True)