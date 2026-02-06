from flask import Flask, request, render_template, redirect, url_for


from .api import fetch_listing_details, search_listings


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("search_form.html.jinja")


@app.route("/search")
def search_results():
    try:
        query = request.args["query"]
    except KeyError:
        return redirect(url_for("index"))

    results = search_listings(query)
    return render_template("search_results.html.jinja", query=query, results=results)


@app.route("/listing/<int:listing_id>")
def listing_details(listing_id: int):
    details = fetch_listing_details(listing_id)
    return render_template("listing_details.html.jinja", **details)
