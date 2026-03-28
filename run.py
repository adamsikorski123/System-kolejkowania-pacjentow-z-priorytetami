from app.init import app


if __name__ == "__main__":
	app.run(debug=True, host="kolejka.local", port=80)
