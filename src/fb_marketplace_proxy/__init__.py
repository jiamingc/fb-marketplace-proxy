from flask import Flask, request, render_template, redirect, url_for


from .api import fetch_listing_details, search_listings, UserViewableError


app = Flask(__name__)
application = app


@app.errorhandler(UserViewableError)
def handle_exception(e: UserViewableError):
    return render_template("error.html.jinja", message=str(e)), 500


@app.route("/")
def index():
    return render_template("search_form.html.jinja")


@app.route("/search")
def search():
    try:
        query = request.args["query"]
    except KeyError:
        return redirect(url_for("index"))

    cursor = request.args.get("cursor")

    results, end_cursor = search_listings(query, cursor)
    return render_template(
        "search_results.html.jinja", query=query, results=results, end_cursor=end_cursor
    )


@app.route("/listing/<int:listing_id>")
def listing_details(listing_id: int):
    details = fetch_listing_details(listing_id)
    return render_template("listing_details.html.jinja", **details)
