from flask import Flask, request, render_template, redirect, url_for, session


from .scraper import Scraper
from .facebook import FacebookClient, FacebookApiError, FacebookAuthCookies


app = Flask(__name__)
application = app
app.secret_key = "test"  # TODO move this into a config


def get_scraper() -> Scraper:
    try:
        auth = FacebookAuthCookies(int(session["c_user"]), session["xs"])
    except KeyError:
        auth = None

    facebook_client = FacebookClient(auth)
    return Scraper(facebook_client)


@app.errorhandler(FacebookApiError)
def handle_exception(e: FacebookApiError):
    return render_template("error.html.jinja", message=str(e)), 500


@app.get("/")
def index():
    return render_template("search_form.html.jinja")


@app.get("/login")
def login_form():
    if "c_user" in session:
        return redirect(url_for("profile"))
    else:
        return render_template("login_form.html.jinja")


@app.get("/profile")
def profile():
    if "c_user" not in session:
        return redirect(url_for("login_form"))
    scraper = get_scraper()
    return render_template("profile.html.jinja", user_name=scraper.get_user_name())


@app.post("/login")
def login():
    # TODO validate credentials
    try:
        auth_cookies = FacebookAuthCookies(
            int(request.form["c_user"]), request.form["xs"]
        )
    except ValueError:
        return redirect(url_for("login"))

    try:
        facebook_client = FacebookClient(auth_cookies)
        facebook_client.CometSettingsDropdownTriggerQuery()
    except FacebookApiError, ValueError:
        return redirect(url_for("login"))

    session["c_user"] = request.form["c_user"]
    session["xs"] = request.form["xs"]
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    print("asdf")
    session.pop("c_user", None)
    session.pop("xs", None)
    return redirect(url_for("login_form"))


@app.get("/search")
def search():
    scraper = get_scraper()
    try:
        query = request.args["query"]
    except KeyError:
        return redirect(url_for("index"))

    cursor = request.args.get("cursor")

    results, end_cursor = scraper.search_listings(query, cursor)
    return render_template(
        "search_results.html.jinja", query=query, results=results, end_cursor=end_cursor
    )


@app.get("/listing/<int:listing_id>")
def listing_details(listing_id: int):
    scraper = get_scraper()
    details = scraper.fetch_listing_details(listing_id)
    return render_template("listing_details.html.jinja", **details)
