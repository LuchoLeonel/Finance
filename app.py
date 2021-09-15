import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date, time, datetime
from math import isnan

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
# Lo comenté para no borrarlo, es lo que traba el inicio sin la API.
#if not os.environ.get("API_KEY"):
#    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    
    # Vamos a bajar a la variable stocks los datos de la TABLA stocks y a la variable user el CASH.
    stocks = db.execute("SELECT symbol, name, number FROM stocks WHERE user_id = ? ORDER BY number DESC", session.get("user_id"))
    user = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))
    # Transformamos el cash a USD.
    user[0]["cash"] = usd(user[0]["cash"])
    
    # Creamos una lista vacia y un loop por cada acción que tengo.
    precio_stocks = []
    for i in range(len(stocks)):
        # Utilizo lookup() para buscar el simbolo y agrego los valores que me da a la lista.
        precio_stocks.append(lookup(stocks[i]["symbol"]))
        # Ademas voy a cambiar el precio por el actual y voy a calcular el total.
        stocks[i]["price"] = usd(precio_stocks[i]["price"])
        stocks[i]["total"] = usd(precio_stocks[i]["price"] * stocks[i]["number"])
    
    # Paso los valores de stock y cash al archivo /index.html.
    return render_template("index.html", stocks=stocks, cash=user[0]["cash"])


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    
    if request.method == "POST":
        # Si no escribió ningun simbolo ni número le retorna error.
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
        
        amount = request.form.get("shares")
        if not amount:
            return apology("must provide a number of shares", 400)
        
        # Chequeamos el número de acciones a comprar no sea un número negativo, flotante ni que tenga letras u otros valores.
        try:
            if int(amount) < 0:
                return apology("must enter a positive number", 400)
            
            if amount.isalpha() == True:
                return apology("must provide a number of shares", 400)
        except (ValueError):
            return apology("must provide a number of shares", 400)
        
        # Si no hay ninguna acción con ese simbolo le avisa que la acción no existe.
        share = lookup(request.form.get("symbol"))
        if not share:
            return apology("this symbol is invalid", 400)
        
        # Bajamos a la variable cash cuanta plata tiene el usuario, y a la variable number la cantidad de acciones que tiene de esa misma acción.
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))
        number = db.execute("SELECT number FROM stocks WHERE user_id = ? and symbol = ?", session.get("user_id"), share["symbol"])
        
        # Multiplicamos el precio por la cantidad que va a comprar, si no le alcanza le avisa.
        cost = share["price"] * int(request.form.get("shares"))
        if cash[0]["cash"] < cost:
            return apology("you are too poor", 400)
        
        # Si le alcanza la plata, le va a descontar del cash que tiene y lo va a guardar en la TABLA users.
        # También va a guardar la transacción en la TABLA transactions.
        cash[0]["cash"] -= cost
        db.execute("INSERT INTO transactions (symbol, user_id, type, number, price, time) VALUES(?, ?, ?, ?, ?, ?)",
                   share["symbol"], session.get("user_id"), "buy", int(request.form.get("shares")), share["price"], datetime.now())
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash[0]["cash"], session.get("user_id"))
        
        # Si cuando buscamos la cantidad de acciones que tenia el usuario, no retorno ningún numero es porque no tiene ninguna acción, y hay que insertar un nuevo registro.
        if not number:
            db.execute("INSERT INTO stocks (symbol, name, user_id, number) VALUES(?, ?, ?, ?)",
                       share["symbol"], share["name"], session.get("user_id"), int(request.form.get("shares")))
        # Si ya tenía esas acciones, solo va a actualizar el número.
        else:
            number[0]["number"] += int(request.form.get("shares"))
            db.execute("UPDATE stocks SET number = ? WHERE user_id = ? and symbol = ?",
                       number[0]["number"], session.get("user_id"), share["symbol"])
        
        return redirect("/")
        
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    
    # Vamos a guardar en la variable stocks la TABLA transactions y lo pasamos al archivo /history.html.
    stocks = db.execute("SELECT symbol, user_id, type, number, price, time FROM transactions WHERE user_id = ? ORDER BY time",
                        session.get("user_id"))
    for i in range(len(stocks)):
        stocks[i]["price"] = usd(stocks[i]["price"])
    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    if request.method == "POST":
        # Si no escribió el symbolo o el número le va a retornar error.
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
        
        # Consulta con lookup() cuál es el valor actual.
        share = lookup(request.form.get("symbol"))
        if not share:
            return apology("must provide symbol", 400)
        
        # Transforma su precio a dolar y pasa la variable al archivo /quoted.html.
        share["price"] = usd(share["price"])
        return render_template("quoted.html", share=share)
        
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    
    if request.method == "POST":
        # Si no escribió username o password le va a retornar error.
        if not request.form.get("username"):
            return apology("must provide username", 400)

        if not request.form.get("password"):
            return apology("must provide password", 400)
        
        # Le avisa que el password debe tener mínimo 8 caracteres.
        if len(request.form.get("password")) < 8:
            return apology("password must have at least 8 characters", 400)
        
        # Le avisa que el password debe tener al menos una letra y un número.
        if not any(chr.isdigit() for chr in request.form.get("password")) or not any(chr.isalpha() for chr in request.form.get("password")):
            return apology("password must have at least 1 letter and 1 number", 400)
        
        # Le avisa que la confirmación debe ser igual a la contraseña.
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("confirmation must be equal to your password", 400)
        
        # Va a chequear si ya existe un usuario con ese nombre.
        users = db.execute("SELECT username FROM users")
        for i in range(len(users)):
            if request.form.get("username") in users[i]["username"]:
                return apology("this user already exists", 400)
        
        # Si está todo bien, va a guardar el usuario dentro de la TABLA users.
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                   request.form.get("username"), generate_password_hash(request.form.get("password")))
        
        return redirect("/login")
        
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    
    if request.method == "POST":
        # Si no escribió simbolo o cantidad de acciones le va a retornar error.
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)
            
        if not request.form.get("shares"):
            return apology("must provide a number of shares", 400)
        
        # Va a guardar en la variable share el precio actualizado de la acción. En la variable cash guarda la cantidad de plata que tiene el usuario.
        # En la variable number guarda la cantidad de esas acciones que tiene actualmente.
        share = lookup(request.form.get("symbol"))
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))
        number = db.execute("SELECT number FROM stocks WHERE user_id = ? and symbol = ?", session.get("user_id"), share["symbol"])
        
        # Si no tiene la cantidad de acciones que quiere vender le va a avisar.
        if number[0]["number"] < int(request.form.get("shares")):
            return apology("you don't have enought stocks", 400)
        
        # Se multiplica el precio actual por la cantidad de acciones que quiere vender.
        total = share["price"] * int(request.form.get("shares"))
        cash[0]["cash"] += total
        
        # Se inserta en la TABLA transactions la información sobre la transacción. Se actualiza la cantidad de cash en la TABLA users.
        db.execute("INSERT INTO transactions (symbol, user_id, type, number, price, time) VALUES(?, ?, ?, ?, ?, ?)",
                   share["symbol"], session.get("user_id"), "sell", int(request.form.get("shares")), share["price"], datetime.now())
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash[0]["cash"], session.get("user_id"))
        
        # Se calcula la nueva cantidad de acciones que tiene y se actualiza la TABLA stocks.
        number[0]["number"] -= int(request.form.get("shares"))
        db.execute("UPDATE stocks SET number = ? WHERE user_id = ? and symbol = ?",
                   number[0]["number"], session.get("user_id"), share["symbol"])
        
        return redirect("/")
        
    else:
        stocks = db.execute("SELECT symbol FROM stocks WHERE user_id = ?", session.get("user_id"))
        return render_template("sell.html", stocks=stocks)


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    """Change password"""
    if request.method == "POST":
        # Si no escribió password le retorna error.
        if not request.form.get("password"):
            return apology("must provide symbol", 400)
        
        # Va a chequear que el password actual ingresado sea el correcto
        rows = db.execute("SELECT hash FROM users WHERE id = ?", session.get("user_id"))
        if not check_password_hash(rows[0]["hash"], request.form.get("actualpassword")):
            return apology("invalid password", 400)
        
        # Le avisa si el nuevo password no tiene 8 caracteres.
        if len(request.form.get("password")) < 8:
            return apology("password must have at least 8 characters", 400)
        
        # Le avisa si el nuevo password no tiene al menos 1 letra y un número.
        if not any(chr.isdigit() for chr in request.form.get("password")) or not any(chr.isalpha() for chr in request.form.get("password")):
            return apology("password must have at least 1 letter and 1 number", 400)
        
        # Chequea que la confirmación sea igual al nuevo password.
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("confirmation must be equal to your password", 400)
        
        # Chequea que el nuevo password no sea igual al anterior password.
        if request.form.get("actualpassword") == request.form.get("password"):
            return apology("new password can't be equal to old password")
        
        # Actualiza el hash de password dentro de la TABLA users.
        db.execute("UPDATE users SET hash = ? WHERE id = ?",
                   generate_password_hash(request.form.get("password")), session.get("user_id"))
        
        return redirect("/")
        
    else:
        return render_template("password.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
