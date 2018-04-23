import os
import requests

from flask import Flask, session, render_template, redirect, request, jsonify
from flask_session import Session

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL") and not os.getenv("GOODREADS_KEY"):
    raise RuntimeError("DATABASE_URL or GOODREADS_KEY is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# make decorator to require login everytime use try to see "user only" info
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


@app.route("/", methods=["POST", "GET"])
@login_required
def index():
    if request.method == "POST":
        # make sure ifіі user types correct query
        if request.form.get("book").replace(" ", "") == "":
            return render_template("error.html", direction="/", error_code= 400,
                                    error_message= "You didn't type any request"), 400
        
        # get any books for given request
        books = db.execute("SELECT title, author, isbn FROM books WHERE LOWER(isbn) LIKE :book OR LOWER(title) LIKE :book OR LOWER(author) LIKE :book",
                          {"book": "%"+request.form.get("book").lower()+"%"}).fetchall()

        # error if nothing has matched
        if books == []:
            return render_template("error.html", error_code= 404, error_message= "Your request didn't give any matches", direction="/"), 404
        
        # render page with results
        return render_template("results.html", books=books, query=request.form.get("book"))

    else:
        return render_template("index.html")


@app.route("/book", methods=["POST", "GET"])
@login_required
def book():
    # get books_id via given in URL isbn
    book_id = db.execute("SELECT id FROM books WHERE isbn = :isbn", {"isbn": request.args.get("isbn")}).fetchone()
    
    # retrieve data about rating of the book on goodreads.com
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": os.getenv("GOODREADS_KEY"), "isbns": request.args.get("isbn")})
    
    # set default of rate doesn't exist
    goodreads= {'books':[{'average_rating':'-'}]}
    
    # if everything is okey set rating to variable
    if res.status_code == 200:
        goodreads = res.json()
    
    # if user post his review and mark
    if request.method == "POST":

        # make exception if user did'nt type neither review nor rate
        if request.form.get("review").replace(" ", "") == "":
            return render_template("error.html", direction="/book?isbn="+request.args.get("isbn"), error_code= 400,
                                    error_message= "You didn't leave a review"), 400
        elif request.form.get("rate").replace(" ", "") == "":
            return render_template("error.html", direction="/book?isbn="+request.args.get("isbn"), error_code= 400,
                                    error_message= "You didn't leave a rate"), 400
        
        # add review to database if user didn't leave any reviewe before
        if db.execute("SELECT review FROM reviews JOIN books ON reviews.book_id = books.id WHERE user_id=:user_id AND isbn=:isbn",
                     {"user_id":session["user_id"], "isbn":request.args.get("isbn")}).fetchall() == []:
            db.execute("INSERT INTO reviews (book_id, user_id, review, mark) VALUES (:book_id, :user_id, :review, :mark)",
                      {"book_id":book_id[0], "user_id":session["user_id"], "review":request.form.get("review"), "mark":request.form.get("rate")})
            db.commit()
        else:
            return render_template("error.html", direction="/book?isbn="+request.args.get("isbn"), error_code= 400,
                                    error_message= "You have a review of this book. You can't do it twice"), 400

    # if user wants to del his review
    if request.args.get("del") != None:
        db.execute("DELETE FROM reviews WHERE user_id = :user_id AND book_id = :book_id" ,
                  {"user_id":session["user_id"], "book_id":book_id[0]})

    # get book's info and reviews from database
    book_info = db.execute("SELECT title, author, year FROM books WHERE isbn=:isbn ", {"isbn": request.args.get("isbn")}).fetchall()
    book_reviews = db.execute("SELECT review, username, user_id, mark FROM reviews JOIN books ON reviews.book_id = books.id JOIN users ON reviews.user_id = users.id WHERE isbn = :isbn",
                             {"isbn":request.args.get("isbn")}).fetchall()
   
    # make switcher if user has left review to show the Delete review button
    session["switcher"] = 0
    for i in book_reviews:
        if session["user_id"] == i[2]:
            session["switcher"] = 1
            break
  
    return render_template("book.html", title=book_info[0][0], author=book_info[0][1], year=book_info[0][2], isbn=request.args.get("isbn"),
                            reviews=list(reversed(book_reviews)), goodreads=goodreads['books'][0]['average_rating'], voters=goodreads['books'][0]['work_ratings_count'])


@app.route("/api/<isbn>")
def api(isbn):
    # get book's info
    book_info = db.execute("SELECT title, author, year FROM books WHERE isbn=:isbn ",
                          {"isbn": isbn}).fetchall()
    
    # return 404 if no info
    if book_info == []:
        return jsonify({"error": "404"}), 404

    # get average rate
    avg_score = db.execute("SELECT AVG(mark) FROM reviews JOIN books ON reviews.book_id = books.id WHERE isbn=:isbn ",
                          {"isbn": isbn}).fetchone()

    # if no marks yet
    if avg_score[0] == None:
        fl_score = "no rates yet"
    else:
        fl_score = float(avg_score[0])
    num_review = db.execute("SELECT COUNT(review) FROM reviews JOIN books ON reviews.book_id = books.id WHERE isbn=:isbn ",
                           {"isbn": isbn}).fetchone()

    return jsonify({
    "title": book_info[0][0],
    "author":  book_info[0][1],
    "year":  book_info[0][2],
    "isbn": isbn,
    "review_count": num_review[0],
    "average_score": fl_score
    })


@app.route("/registration", methods=["POST", "GET"])
def registration():
    if request.method == "POST":

        # check if username exists
        if db.execute("SELECT * FROM users WHERE username = :username", {"username": request.form.get("username")}).fetchall() != []:
            return render_template("error.html", direction="/registration", error_code= 400, error_message= "Username exists"), 400
        
        # make some warnings if username or pass or 2nd pass is missed or paswords doesn't match
        elif not request.form.get("username").isalnum():
            return render_template("error.html", direction="/registration", error_code= 400,
                                    error_message= "You should type your username or it doesn't contain alphanumeric symbols"), 400
        
        elif not request.form.get("password").isalnum():
            return render_template("error.html", direction="/registration", error_code= 400,
                                    error_message= "You should type your password or it doesn't contain alphanumeric symbols"), 400
        
        elif not request.form.get("re_password").isalnum():
            return render_template("error.html", direction="/registration", error_code= 400, error_message= "You should type your password again"), 400
        
        elif request.form.get("re_password") != request.form.get("password"):
            return render_template("error.html", direction="/registration", error_code= 400, error_message= "You should type identical passwords"), 400


        # let's generate hash for gotten password
        hashed_pass = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, password) VALUES (:username, :password)", {"username": request.form.get("username"), "password": hashed_pass})
        db.commit()

        # return page about succesfull registration
        return render_template("success.html", direction="/login", success_message="You were registered!", direct_message="Log in")
    
    else:
        
        return render_template("registration.html")



@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        # check if username exists in database
        if db.execute("SELECT * FROM users WHERE username = :username", {"username": request.form.get("username")}).fetchall() == []:
            return render_template("error.html", direction="/login", error_code= 400, error_message= "Username doesn't exist"), 400
        
        # get hashed password 
        hashed_pass = db.execute("SELECT password FROM users WHERE username = :username", {"username": request.form.get("username")}).fetchall()

        # check if there is correct password
        if not check_password_hash(hashed_pass[0][0], request.form.get("password")):
            return render_template("error.html", direction="/login", error_code= 400, error_message= "Password is not correct"), 400
        
        # set user id for his session
        user_id = db.execute("SELECT id FROM users WHERE username = :username", {"username": request.form.get("username")}).fetchall()
        session["user_id"] = user_id[0][0]

        return render_template("success.html", direction="/", success_message="You were logged in!", direct_message="Main page")
    else:

        return render_template("login.html")

@app.route("/logout")
@login_required
def logout():

    session.clear()
    return redirect("/")



