module lemma-enterprise

go 1.18

require (
	github.com/gorilla/mux v1.8.0
) 

// Make the oprfservice buildable as a separate module
replace github.com/lemma/oprf-service => ./oprfservice

// +heroku install ./oprfservice 