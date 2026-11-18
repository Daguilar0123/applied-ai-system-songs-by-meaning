# 🎧 Model Card: Songs by Meaning

## Model name

**Songs by Meaning 1.0.** It is the recommender from my Project 3, Sad But Loud 1.0, with search by meaning added: you type what a song is about, the system finds the closest lyric verses and song descriptions, and Gemini names the song and explains the match using only what was found.

The Project 3 model card, as submitted, is kept in full in [`docs/PROJECT3_model_card.md`](docs/PROJECT3_model_card.md). It covers the recommender's data, scoring, evaluation and biases. How the new search works, with the diagram and sample runs, is in the [README](README.md).

## Limitations and biases

This is a small model of the system I wanted to build, not a production system. The library has ten songs, so the search only works for a few songs and a few meanings. That is on purpose. The project is meant to demonstrate search by meaning instead of search by keyword, not to be a full recommender. It also adds tests to the recommender from Project 3.

The mood and energy values for the library songs are estimates that an AI proposed and I accepted. They are not measured. The descriptions of the five modern songs were drafted by a small Gemini model from Wikipedia articles, and I reviewed them. A small model is not going to be accurate about everything.

The stakes are low, but a wrong answer could be embarrassing. If a DJ or someone picking a song for an event needed a certain mood and the system gave them the opposite, that would be about the biggest risk. Nothing dangerous happens. The system just would not work.

The bias that matters most is cultural. Songs come from specific groups and from cultural events. Spirituals came out of slavery, and slaves used them to communicate with each other and to encourage each other. When a model writes what a song means from statistical averages, it does not have the perspective of that community.

## Misuse and prevention

I want to answer this for the system I wanted to build and for the one I built. The system I wanted uses a vector database of song lyrics and descriptions to find songs by meaning. What I built is a small model of that system with a few curated songs, and for the demo I am the only user.

I don't think there are many ways to misuse a search like this. The main one is that a person can type whatever they want, including instructions meant for the AI, and that could waste API tokens. The design limits this in code, before any AI call. The request is turned into numbers by a local model that costs nothing. Gemini is only called when the search finds a close match, and an empty request makes no call at all. A request over 300 characters is refused. A checker rejects an answer that names a song the search did not return. In a real product with many users, I would add a limit on how many searches one person can run.

## What surprised me in testing

I wanted to see if the system really worked, so I changed the search terms from the example to my own. I typed "caramel popcorn and live sports" and it found Take Me Out to the Ball Game. The answer explained that the snack named in the song is a caramel popcorn. That gave me an idea for the demo: show the class the list of songs, ask them to describe one in their own words, and run their words as the search.

Testing also showed where it fails. "The greengrocer who has no fruit" returned Fast Car, not the bananas song, with a score above the line. A search about being lost and then forgiven ranked Fast Car above Amazing Grace, and the AI answer still picked Amazing Grace from the top three. A search for a song that is not in the library returned Jolene when it should have said nothing close was found. The descriptions of modern songs are written in today's language and score close to almost any request, while the old lyrics are in older verse and get missed more. If a search doesn't work, the trace at least gives an explanation that can be examined.

## Collaboration with AI

I read the project instructions, looked at my Project 3 repo, and made the decisions about what to build. AI sessions wrote the plans, the prompts and the code from those decisions, and I reviewed the code and ran every git command myself. I also had a separate AI session write the test searches before it saw the search code, and I approved the expected answer for each one.

One suggestion I rejected: the AI proposed a demo that searched by vibe, where keyword matching fails and vector search wins. I didn't want to do exactly what the TF had done in the example demo, which was a search by energy and vibes. I kept the idea of meaning beating keywords and chose to search by the meaning of lyrics.

One suggestion I accepted: using Wikipedia as the base for the song descriptions, because its license allows the text to be reused with credit.

One suggestion I accepted at first and then changed: the AI recommended not storing actual lyrics that are still under copyright, because the repo is public. After thinking it through, I told the AI that the repo is public but I won't be sharing it, it won't be posted to any website, it is not for profit, and it is strictly for education, so it could use real lyrics. By then the five lyric songs were already public-domain songs and the five modern songs were stored as descriptions, so that decision came too late to change what was built.

Where AI helped me most was time management. I sometimes struggle with it, and it showed here. The AI told me several times that we needed to keep going and that the deadline was close. That kept me on track so that I didn't miss the assignment.

## Testing results

104 automated tests pass: the 43 from Project 3 and 61 new ones. The evaluation script (`python -m src.evaluate`) runs ten searches that I approved. Full tables are in `evals/results.md`.

| What was measured | Result |
|---|---|
| Searches sharing no important word with the song: word matching found it | 1 of 4 |
| Searches sharing no important word with the song: meaning search found it | 4 of 4 (ranked first 3 of 4) |
| Control searches that share words with the song | 2 of 2 for both methods |
| Guardrail cases passed | 3 of 4 |
| Same search run twice, same result | 10 of 10 |
| Quoted text found in a retrieved document | 8 of 8 |
| Bad replies made on purpose, rejected by the checker | 5 of 5 |

The guardrail that failed: a search for "Bohemian Rhapsody by Queen", which is not in the library, returned Jolene at 0.807, above the 0.78 line, when it should have said nothing close was found.
