module lemma-enterprise

go 1.18

require (
	github.com/gorilla/mux v1.8.0
	github.com/lemma/oprf-service v0.0.0-00010101000000-000000000000
)

// Make the oprfservice buildable as a separate module
replace github.com/lemma/oprf-service => ./oprfservice

// +heroku install ./oprfservice 