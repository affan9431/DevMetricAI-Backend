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
            {"input": 's = ["h","e","l","l","o"]',
                "output": '["o","l","l","e","h"]'},
            {"input": 's = ["H","a","n","n","a","h"]',
                "output": '["h","a","n","n","a","H"]'},
        ],
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
        model="gemini-2.0-flash", contents=f"Generate five coding questions for DSA, including hard, medium, and easy questions at FAANG interview level and give questions in the form {problems} but don't include this question this is just a example all 5 questions are new and match the level of FAANG coding questions."
    )
    return response.text


def evaluate_user_code(allCode):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=(
            f"Evaluate the following code snippet thoroughly based on:\n"
            f"- **Correctness** (Does it function as expected?)\n"
            f"- **Efficiency** (Are there unnecessary computations? Can it be optimized?)\n"
            f"- **Best Practices** (Does it follow clean coding standards, readability, and maintainability?)\n"
            f"- **Edge Cases** (Are there scenarios where the code might fail or behave unexpectedly?)\n"
            f"- **Error Handling** (Are there cases where the code throws errors? How can they be fixed?)\n"
            f"- **Alternative Approaches** (Are there better ways to solve the problem?)\n\n"

            f"### **User's Code:**\n\n```javascript\n{allCode}\n```\n\n"

            f"#### **Response Format:**\n"
            f"Return a **valid JSON object** with the following structure:\n"
            f"```json\n"
            f"{{\n"
            f"  \"evaluations\": [\n"
            f"    {{\n"
            f"      \"questionId\": <question_id>,\n"
            f"      \"questionTitle\": \"<title>\",\n"
            f"      \"score\": <integer_out_of_10>,\n"
            f"      \"feedback\": \"<detailed_feedback>\",\n"
            f"      \"capability\": \"<Beginner/Intermediate/Advanced>\",\n"
            f"      \"improvements\": \"<List improvements or optimizations>\",\n"
            f"      \"potentialErrors\": \"<List scenarios where this code might throw errors>\",\n"
            f"      \"edgeCases\": \"<Mention edge cases that may break the code>\",\n"
            f"      \"alternativeApproach\": \"<Suggest a different or more optimized approach>\"\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"```\n"
            f"Ensure the output is a **valid JSON object**, not an array of objects."
        )
    )
    return response.text


# Maintain conversation history as a global variable or database storage
conversation_history = []


def generate_interview_question(answer: str, extracted_skills: list, domain: str, project: str, stopInterview) -> str:
    global conversation_history

    if stopInterview == "true":
        prompt = f"""Generate a FAANG-level technical interview question considering:
        1. User's skills: {extracted_skills}
        2. Previous conversation context (most recent first): {conversation_history[-3:]}
        3. Their latest answer: "{answer}"
        4. Domain: {domain}
        5. Project {project}
        
        Follow these rules:
        - Start with introduction questions if the conversation is just beginning.
        - Then move to easy technical questions based on their skills.
        - Gradually increase difficulty based on their responses and skill level.
        - If the user gives a strong technical answer, ask a deeper follow-up on implementation, edge cases, or alternative approaches.
        - Never repeat questions.
        - Prioritize topics related to {extracted_skills[-5:]}.
        - Keep questions under 2 sentences.
        - Ask questions from their project as well.
        - Format: [optional brief reaction] [question]"""

        # Generate response using Gemini API
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )

        generated_question = response.text

        # Update conversation history
        conversation_history.append({
            'user_answer': answer,
            'generated_question': generated_question
        })

        return generated_question
    else:
        score_prompt = f"""
        Analyze the conversation history and evaluate the user's performance.
        
        1. Assign marks to each answer, ensuring the total score does not exceed 50.
        2. Consider depth, correctness, edge cases, and alternative approaches.
        3. Provide overall feedback summarizing performance.
        4. Return a single JSON object with total marks and final feedback.
        
        Conversation History: {conversation_history}
        
        Format: 
        {{
        "TotalMarks": X,  
        "Feedback": "<Overall performance summary>"
        }}
        Ensure that X is a single integer score out of 50.
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=score_prompt
        )

        return response.text


def predict_domain_based_on_skills(skills):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"Predict the domain of a software engineer based on the following skills: {skills} and return in one word like Full Stack web developer, Machine Laerning Developer and so on."
    )
    return response.text


def predict_user_strength_and_weakness(data):
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""
        Analyze the following user data: {data}. Identify exactly three strengths and three weaknesses based on coding scores, interview performance, and other relevant factors.

        Return the response in JavaScript array format with concise statements, similar to "Great at problem-solving questions" or "Struggles with system design questions."

        ```js
        [
          "✔️ Great at problem-solving questions",
          "✔️ Strong logical reasoning skills",
          "✔️ Confident in data structures & algorithms"
        ]
        ```

        ```js
        [
          "❌ Struggles with system design questions",
          "❌ Needs improvement in behavioral answers",
          "❌ Sometimes lacks structured responses"
        ]
        ```
        """
    )
    return response.text
