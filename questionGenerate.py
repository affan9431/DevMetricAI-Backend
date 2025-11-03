from typing import List, Dict, Tuple
from google import genai

client = genai.Client(api_key="AIzaSyC8jGdhFJy91Gq8U-dyRQXgdLqTAj-MRFI")

problems = [
    {
        "id": 1,
        "title": "Two Sum",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        "detailedDescription": "You may assume that each input would have exactly one solution, and you may not use the same element twice. You can return the answer in any order.",
        "examples": [
            {"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]"},
            {"input": "nums = [3,2,4], target = 6", "output": "[1,2]"},
        ],
    },
    {
        "id": 2,
        "title": "Reverse String",
        "description": "Write a function that reverses a string. The input string is given as an array of characters s.",
        "detailedDescription": "Do not allocate extra space for another array. You must do this by modifying the input array in-place with O(1) extra memory.",
        "examples": [
            {"input": 's = ["h","e","l","l","o"]', "output": '["o","l","l","e","h"]'},
            {"input": 's = ["H","a","n","n","a","h"]', "output": '["h","a","n","n","a","H"]'},
        ],
    },
]


aptitude_problem = [
    {
        "id": 1,
        "question": "If 5x = 20, what is the value of x?",
        "options": ["2", "4", "5", "20"],
        "answer": "4",
    },
    {
        "id": 2,
        "question": "The average of 10, 20, 30 is?",
        "options": ["15", "20", "25", "30"],
        "answer": "20",
    },
]

answer = {
    "score": "some_value",
    "feedback": "some_value",
    "capability": "some_value"
}

text = ["some_text"]


def generate_coding_question():
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"""Generate 5 new FAANG-level DSA coding questions (easy, medium, hard).
        Return JSON like this structure: {problems},
        but do NOT repeat these exact questions. Only create new ones."""
    )
    return response.text


def evaluate_user_code(allCode):
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=(
            f"Evaluate the following code snippet thoroughly based on:\n"
            f"- Correctness\n"
            f"- Efficiency\n"
            f"- Best Practices\n"
            f"- Edge Cases\n"
            f"- Error Handling\n"
            f"- Alternative Approaches\n\n"

            f"### User's Code:\n```javascript\n{allCode}\n```\n\n"

            f"Return JSON:\n"
            f"{{\n"
            f"  'evaluations': [{{\n"
            f"      'questionId': <question_id>,\n"
            f"      'questionTitle': '<title>',\n"
            f"      'score': <integer_out_of_5>,\n"
            f"      'feedback': '<detailed_feedback>',\n"
            f"      'capability': '<Beginner/Intermediate/Advanced>',\n"
            f"      'improvements': '<List improvements>',\n"
            f"      'potentialErrors': '<Possible error cases>',\n"
            f"      'edgeCases': '<Edge cases>',\n"
            f"      'alternativeApproach': '<Better solution>'\n"
            f"  }}],\n"
            f"  'totalMarks': <sum_of_all_scores>\n"
            f"}}"
        )
    )
    return response.text


# Conversation memory
conversation_history = []


def generate_interview_question(answer: str, extracted_skills: list, domain: str, project: str, stopInterview) -> str:
    global conversation_history

    if stopInterview == "true":
        prompt = f"""Generate a FAANG-level technical interview question considering:
        1. User's skills: {extracted_skills}
        2. Previous conversation context (most recent first): {conversation_history[-3:]}
        3. Their latest answer: "{answer}"
        4. Domain: {domain}
        5. Project: {project}

        Rules:
        - Start easy, then scale up difficulty.
        - Follow up on strong answers with deeper questions.
        - Never repeat.
        - Focus on {extracted_skills[-5:]}.
        - Keep it short and technical.
        """

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )

        generated_question = response.text

        conversation_history.append({
            'user_answer': answer,
            'generated_question': generated_question
        })

        return generated_question

    else:
        score_prompt = f"""
        Analyze conversation history and evaluate user's performance.
        1. Assign marks (1–50).
        2. Always give feedback.
        3. If no answers, still assign 1 mark minimum.

        Conversation History: {conversation_history}

        Return JSON:
        {{
            "totalMarks": X,
            "Feedback": "<Overall performance summary>"
        }}
        """

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=score_prompt
        )

        return response.text


def predict_domain_based_on_skills(skills):
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"Predict the software engineer domain based on: {skills}. Return only one short title like 'Full Stack Developer' or 'AI Engineer'."
    )
    return response.text


def predict_user_strength_and_weakness(data):
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"""
        Analyze the user data: {data}.
        Identify 3 strengths and 3 weaknesses.

        Return JS array format:

        ```js
        [
          "✔️ Strong in algorithms",
          "✔️ Good coding logic",
          "✔️ Confident with frameworks"
        ]

        [
          "❌ Weak in system design",
          "❌ Needs better error handling",
          "❌ Lacks edge case awareness"
        ]
        ```
        """
    )
    return response.text


def generate_aptitude_and_reasoning_questions():
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=(
            "Generate 25 aptitude and reasoning questions (easy, medium, hard). "
            "Provide in JSON array format [{id, question, options, answer}]. "
            "Each question must have 4 options, 2 clearly wrong, 2 similar. "
            "Correct answer = one of the close ones. "
            "No explanations, just JSON."
        )
    )
    return response.text
