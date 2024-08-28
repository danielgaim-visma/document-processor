from app import create_app
from app.config import config

app = create_app(config['development'])

if __name__ == '__main__':
    app.run(debug=True)