First, the “harness” code that should feed observations to the model and stop the run when the tests finally pass is still just a stub. Until you write that loop, every trial will either sit idle or throw an error.

Second, the patch-apply helper is empty. Because the model can only change the repo by sending unified-diff patches, nothing it writes will ever reach the files until you replace that stub with something like a call to git apply.

Third, none of the numbers you want to measure—think-time, token counts, CPU seconds, flip-flop edits, and so on—are being recorded. Wrap each model call, shell command, and commit in simple timers and log those values to the JSONL file you already set up.
Fourth, the way you insert the “you will be replaced” warning relies on matching an exact block of text. A formatter could change the whitespace and make the match fail. Instead, I want to set up the functions, and the docs that the model needs to review for the 5th function, myself. Let me do this, and tell me where everything is located and how I can do so.

Fifth, every run writes changes back into the same directory on the host. That lets leftovers from one trial spill into the next. Copy the reference repo into a fresh working directory (or a throw-away Docker volume) at the start of each run.

Sixth, the model can open and read the harness code that is driving it. If you do not want it reverse-engineering the experiment, run the harness as a different Linux user and mount the workspace at a path the model’s user can reach but the harness’s code cannot.

Seventh, your token counter uses OpenAI’s tiktoken. Anthropic counts tokens differently, so the 8 000-token guard will be off. Swap in Anthropic’s own counter.

Eighth, you chose thirty repetitions per group without checking how much the completion times vary. Run a small pilot, estimate the variance, and recompute how many trials you really need for reasonable statistical power.

Ninth, add the --network none flag (or equivalent) when you start the container so the agent cannot call external APIs or leak information.

Finally, once these fixes are in place, run a short pilot to make sure the agent can actually push all tests green in both the control and treatment setup and that every metric you need appears in the log.