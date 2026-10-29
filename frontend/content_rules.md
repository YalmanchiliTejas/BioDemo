# How we write: clear, natural narration

Applies to narration, on-screen text, exercises and the book. The spoken-language guidance below is for narration;
adapt it to the format when writing on-screen text, exercises or the book. `python3 -m engine.lint <video_dir>`
(Stage 3 and Stage 4) flags mechanical patterns in `script.md` narration. Review those flags in context. The linter
currently flags sentences over 20 words; that is a review prompt, not an automatic failure. Record why a flagged
sentence is kept. A script also needs the read-aloud and cross-lesson review below: zero flags alone does not make
it ready.

**Why:** viewers distrust text that sounds machine-written, and these patterns add words without adding meaning
(LEARNING B5, coherence). The user asked for this on 2026-10-17. The patterns come from Wikipedia's editor guide
*Signs of AI writing* and from writing-style surveys (sources below). None of them proves a text is AI-written; they
are habits to avoid.

## Never

1. **Negative parallelism.** "Not X, but Y", "not just X, but also Y", "it's not X, it's Y", "X rather than Y", and
   chains such as "not one, not two, but ten". Say what *is* true, directly: "Eleven rows hold a space."
2. **AI vocabulary.** delve, tapestry, testament, pivotal, underscore, showcase, realm, landscape, embark, vibrant,
   intricate, meticulous, seamless, robust, leverage, unlock, elevate, foster, navigate (anything not a map),
   game-changer, crucial, groundbreaking, ever-evolving, "dive into", "it's important to note", "in summary",
   "in conclusion".
3. **Puffery and flourish.** Words that praise instead of inform: "honest", "beautiful", "elegant", "magic",
   "powerful", "the secret", "the truth is", "here's the thing". Name the fact instead.
4. **"Serves as" / "stands as" / "boasts".** Use "is" and "has".
5. **Trailing "-ing" commentary.** "…, highlighting the importance of …", "…, ensuring that …". End the sentence.
6. **Reflexive rule of three.** One list of three is fine; a script built on triplets is not. Use the number of items
   that exists.
7. **Em dashes in narration.** Use a full stop or a comma. (The voice reads punctuation, and dashes read as a tell.)
8. **Recaps and outline endings.** No "So, to sum up". A video ends on a question the viewer answers (LEARNING C1).

## Always

- Use familiar words, clear references and active voice. Let sentence length follow the explanation. Combine related
  thoughts when they sound more natural aloud. Review sentences over 20 words for clarity, breath and listening
  effort; keep them when they are easy to follow. Do not shorten a sentence by removing necessary words or chopping
  a connected thought into fragments.
- Concrete numbers from our own checked data: "eleven rows", not "several rows".
- Talk to one viewer: "you", "let's" (LEARNING B9). Plain verbs: is, has, shows, counts.

## Natural spoken narration

Write as a knowledgeable teacher explaining a specific example to one learner. Explain the subject directly.
Use the following checks to catch rigid phrasing that a vocabulary checker will miss.

1. **Explain the reasoning behind a mistake.** Show the specific inference that leads to the wrong answer
   (LEARNING B2). Describe possible mistakes conditionally: "You might choose A because..." Avoid unsupported
   claims about the audience, such as "Many people pick A", and awkward labels such as "Why does A tempt?"
   Explain what makes the answer plausible without repeatedly describing the learner's feelings.
2. **Connect ideas with concrete transitions.** State the next action or the reason for it: "Drop the blank rows
   and compare the averages." Remove generic signposts such as "Now back to the opening question" when they add
   no useful connection. Keep callbacks that help the learner recall a relevant picture (LEARNING A5).
3. **Let the explanation determine the sentence structure.** Use complete, connected thoughts. Review repeated
   slogans, balanced phrases and punchy fragments across the script. Keep a short phrase when it helps a listener
   understand or remember the idea; do not make every explanation sound like a tagline. Prefer direct, complete
   explanations over slogan-like fragments. Avoid compressed patterns such as "Same X, two Y, different Z." Keep
   sentences conversational without turning them into taglines. (The user's rule, 2026-10-18.)
4. **Describe what the data or model does.** Use a metaphor when it clarifies a mechanism, then make the literal
   meaning clear. Replace decorative personification when the actual sequence of events is easier to understand.
5. **Keep the teaching structure; vary its expression.** Preserve the hook, callback, pause question, reveal,
   retrieval question and forward link required by LEARNING.md. Read adjacent lessons together and flag repeated
   wording such as "A is tempting", "Quick check, from memory" and "In week...". Keep repetition that supports
   learning, including consistent technical terms. Revise repeated framing that merely fills a template. Do not
   swap in synonyms just to make lessons look different.
6. **Preserve technical qualifications.** Conversational wording must retain distinctions between evidence and
   proof, association and causation, and an example and a general rule. A shorter sentence is not an improvement
   if it turns a qualified claim into an absolute one.
7. **Use ordinary spoken language.** Read the narration aloud and revise phrases that are awkward to say or hard
   to follow on first hearing. Contractions are welcome where natural. Do not manufacture informality with slang,
   filler, deliberate errors or forced contractions. Clear, natural sentences can stay as written.

### Examples

| Before | More natural |
|---|---|
| "Why does A tempt?" | "Seventy-three percent sounds good if you compare it with a coin flip." |
| "Deleting feels like cleaning, and the word flagged sounds a lot like wrong." | "It's easy to read 'flagged' as 'wrong' and delete those rows." |
| "The refund already knew the ending." | "The table includes refunds issued after customers left." |
| "Same column, two rules, different lists." | "The two rules look at the same column, but they flag different customers." |

### Final editing pass

- Read the narration aloud. Check sentence flow, references, breath and whether the explanation makes sense on
  first hearing. Review long sentences without imposing a fixed word limit.
- Check each paragraph for an observation, action, reason, consequence or useful question. Cut framing that adds
  nothing to the explanation.
- Check claims about what the learner thinks or feels. Explain the possible reasoning instead.
- Compare adjacent lessons for repeated transitions and rhetorical patterns. Preserve purposeful repetition and
  required teaching elements.
- Confirm that every rewrite preserves the checked numbers, technical meaning and necessary uncertainty.

## Sources

- Wikipedia, [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (editor guide):
  negative parallelisms, rule of three, AI vocabulary, avoidance of basic copulatives, superficial "-ing" analyses,
  promotional language, outline-like conclusions, em dashes.
- Juzek & Ward, *Why does ChatGPT "delve" so much?*, COLING 2025 (21 words whose use in scientific abstracts spiked):
  [summary](https://www.newswise.com/articles/why-does-chatgpt-delve-so-much-fsu-researchers-begin-to-uncover-why-chatgpt-overuses-certain-words).
- [The Conversation](https://theconversation.com/chatgpt-is-changing-the-way-we-write-heres-how-and-why-its-a-problem-239601)
  on words that surged after ChatGPT ("delves", "showcasing", "underscores", "pivotal", "realm", "meticulous").
- Project editorial review (2026-10-18): natural narration guidance and examples drawn from the Gate S scripts.
  These are editorial preferences, not a test of whether a text was written by AI.