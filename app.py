import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from pytz import timezone

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get the stock portfolio from the stock database for the current user.
    rows = db.execute("SELECT symbol, SUM(shares) AS total_shares, price, SUM(shares * price) AS total FROM stocks WHERE user_id = (?) GROUP BY symbol, price HAVING SUM(shares) != 0", session["user_id"])


    # Get the cash amount the user has left.
    usercash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])
    cash_amount = round((usercash[0]['cash']),2)

    # Get the sum of all stocks owned by user.
    stock_total_amount_rows = db.execute("SELECT (shares * price) AS total FROM stocks WHERE user_id = (?)", session["user_id"])

    amount_total = 0
    for amount in stock_total_amount_rows:
        amount_total += amount['total']

    total = amount_total + cash_amount
    total = round(total,2)
    return render_template("index.html", purschases=rows, cash=cash_amount, amount=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        shares = int(request.form.get("shares"))
        symbol = request.form.get("symbol")
        symbol = symbol.upper()
        lookupresult = lookup(symbol)

        # Check if user submitted a symbol and if the symbol is valid
        if not symbol or lookupresult == None:
            return apology("Must submit a valid Symbol", 400)

        if not shares:
            return apology("Must submit a valid number of shares", 400)

        if not isinstance(shares, int) or shares < 1:
            return apology("Must provide a valid number of shares", 400)

        # Store the final price of the shares the user wants to buy
        stockfullprice = lookupresult["price"] * shares
        stockprice = lookupresult["price"]

        # Get the user cash available amount
        usercash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])
        cash_amount = float(usercash[0]['cash'])

        # Check if user has enough money to buy the stocks.
        if stockfullprice > cash_amount:
            return apology("Can't Afford", 403)

        # Gets the date and exact hour the user made the transaction
        now = datetime.now(timezone('America/New_York'))
        now = now.strftime('%Y-%m-%d %H:%M:%S')

        # insert purschase to the stocks database.
        db.execute("INSERT INTO stocks (symbol, shares, price, time, user_id) VALUES (?, ?, ?, ?, ?)", symbol, shares, stockprice, now, session["user_id"])

        new_amount = cash_amount - stockfullprice

        # Update the cash balance of the user after the purschase.
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", new_amount,session["user_id"])

        return redirect("/")

    else:
        return render_template("/buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("SELECT symbol, shares, price, time FROM stocks WHERE user_id = (?)", session["user_id"])

    return render_template("history.html", transactions=rows)


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
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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

    # If user submitted a Quote
    if request.method == "POST":

        symbol = request.form.get("symbol")
        lookupresult = lookup(symbol)

        # Check if user submitted a symbol and if the symbol is valid
        if not symbol or lookupresult == None:
            return apology("Must submit a valid Symbol", 400)

        # render the result of the internet lookup.
        return render_template("quoted.html", result=lookupresult)
    else:

        # If user got to quote via GET, just display Quote form (quote.html)
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # If user has submit the registration form.
    if request.method == "POST":

        # If the user has submitted a username
        if not request.form.get("username"):
            return apology("Must insert username", 400)

        # Check if user submitted a password
        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("Must insert password and confirm it", 400)

        # Check if passwords inserted match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords don't match", 400)

        #hash password
        hash = generate_password_hash(request.form.get("password"))

        # Check if user name is duplicated
        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), hash)
        except ValueError:
            return apology("Username already exists", 400)

        # Go back home with the registration completed
        return redirect("/")

    # If user click on the register button and didnt submit anything yet. Just render the registration page.
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Gets the selected symbol to sell by the user.
        symbol = request.form.get("symbol")

        # Gets the amount of shares the user wants to sell.
        shares_to_sell = request.form.get("shares")

        # Checks if the user has inputed a symbol and an amount of shares.
        if not symbol:
            return apology("Must select a stock to sell", 400)
        if not shares_to_sell:
            return apology("Must insert amount of shares to sell", 400)

        # Gets the available amount of shares the user has of the selected symbol.
        available_share_rows = db.execute("SELECT SUM(shares) AS total_shares FROM stocks WHERE user_id = (?) AND symbol = (?)", session["user_id"], symbol)
        available_shares_row = available_share_rows[0]
        available_shares = available_shares_row['total_shares']

        # Checks if the user has enough shares to sell of that particular symbol.
        if int(shares_to_sell) > available_shares:
            return apology("Not enough shares to sell", 403)

        #convert sales into negative numbers
        shares_to_sell = float(shares_to_sell)*(-1)

        #get stock current price
        lookupresult = lookup(symbol)
        stockprice = lookupresult["price"]

        #get the stock full price of the sale to update the user cash in the users database later on.
        stockfullprice = lookupresult["price"] * shares_to_sell

        #Get the transaction time
        now = datetime.now(timezone('America/New_York'))
        now = now.strftime('%Y-%m-%d %H:%M:%S')

        # Updates the stocks database.
        db.execute("INSERT INTO stocks (symbol, shares, price, time, user_id) VALUES (?, ?, ?, ?, ?)", symbol, shares_to_sell, stockprice, now, session["user_id"])

        # Get the user cash available amount
        usercash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])
        cash_amount = float(usercash[0]['cash'])
        new_amount = cash_amount - stockfullprice

        # Updates user cash database.
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", new_amount,session["user_id"])

        return redirect("/")


    else:

        # Get all stocks the user has available for sale.
        rows = db.execute("SELECT DISTINCT symbol FROM stocks WHERE user_id = (?)", session["user_id"])

        return render_template("sell.html", symbols=rows)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Add cash to the user account"""
    if request.method == "POST":

        # Get user amount available
        usercash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])
        cash_amount = float(usercash[0]['cash'])

        # Get user amount of cash to add to his account.
        deposit = float(request.form.get("cash"))

        # Get the total new amount
        new_amount = cash_amount + deposit

        # Updates user cash database.
        db.execute("UPDATE users SET cash = (?) WHERE id = (?)", new_amount,session["user_id"])

        return redirect("/")
    else:
        return render_template("deposit.html")
