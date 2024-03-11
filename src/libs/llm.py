from openai import OpenAI
from .tokens import num_tokens_from_string


# Create an instance of the OpenAI class
client = OpenAI()


def condense_transcript(transcript, attendee_list):
    condensed_text = ""
    previous_speaker = None

    for line in transcript:
        try:
            if ":" in line:
                speaker, text = line.split(": ", 1)

                # Skip short lines
                if len(text) < 15:
                    continue

                if speaker in attendee_list:

                    # Remove leading/trailing whitespaces
                    speaker = speaker.strip()
                    text = text.strip()

                    # Condense consecutive lines from the same speaker
                    if speaker == previous_speaker:
                        condensed_text += " " + text
                    else:
                        # Add a new line for a new speaker
                        condensed_text += "\n" + line.strip()

                    previous_speaker = speaker
                else:
                    # Add a new line for lines that don't have a colon
                    condensed_text += "\n" + line
            else:
                # Add a new line for lines that don't have a colon
                # condensed_text += "\n" + line
                pass
        except ValueError:
            # Skip lines that don't have a colon
            pass

    return condensed_text.strip()


def summarize_text(text: str, max_tokens: int = 4000) -> str:
    system = "\n".join([
        "You are a meeting assistant who is an expert in summarizing meeting transcripts.",
        "Your specialty is to summarize chunks of lines of text from a meeting transcript generated by a computer that may contain errors.",
        "You know how to summarize partial transcripts and maintain the conversational structure and action items.",
        "Always include the speaker's name and a colon before the summary of what was said. Use ONLY one short sentence to summarize each speaker if possible.",
        "Remember to keep the summary short and concise while retaining information about discussion topics, key descisions and action items.",
    ])

    summary_response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        temperature=0,
        max_tokens=max_tokens or 2000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f'"""{text}"""\n\nSummarize the transcript above.'},
        ]
    )
    summary = summary_response.choices[0].message.content
    # print(summary)
    return summary


def summarize_lines_in_chunks(lines, chunk_size=20):
    # Split the lines into chunks
    chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]

    # Summarize each chunk
    summaries = []
    for i, chunk in enumerate(chunks):
        print(f"Summarizing chunk {i + 1} of {len(chunks)}")
        summary = summarize_text("\n".join(chunk))
        summaries.append(summary)

    return summaries


def summarize_long_text_in_chunks(text):
    # Split the text into lines
    lines = text.split("\n")

    # Set counters
    tokens = 0
    chunks = []
    chunk_lines = []

    # Split the lines into chunks that are less than 13000 tokens
    for line in lines:
        line_tokens = num_tokens_from_string(line, "gpt-3.5-turbo")
        if tokens + line_tokens > 50000:
            chunks.append("\n".join(chunk_lines))
            chunk_lines = []
            tokens = 0
        else:
            chunk_lines.append(line)
            tokens += line_tokens

    # Add the last chunk
    chunks.append("\n".join(chunk_lines))

    # Summarize each chunk
    summaries = []
    for i, chunk in enumerate(chunks):
        print(f"Summarizing chunk {i + 1} of {len(chunks)}")
        summary = summarize_text(chunk)
        summaries.append(summary)

    # Combine the summaries
    summary = "\n".join(summaries)

    # Check if the last summary is too long
    if num_tokens_from_string(summary, "gpt-3.5-turbo") > 100000:
        # Summarize the summary
        return summarize_long_text_in_chunks(summary)

    # Return the summary
    return summary
