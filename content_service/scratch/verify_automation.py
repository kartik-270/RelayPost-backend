from automation.prompts import TOPIC_BRAINSTORM_PROMPT, CONTENT_GENERATION_PROMPT
import asyncio

async def test_prompts():
    print("Testing Prompts Formatting...")
    
    # Test Brainstorm Prompt
    categories = "Tech, Business, Science"
    existing_topics = "Topic A, Topic B"
    existing_keywords = "KW1, KW2"
    
    brainstorm_prompt = TOPIC_BRAINSTORM_PROMPT.format(
        categories=categories,
        existing_topics=existing_topics,
        existing_keywords=existing_keywords
    )
    print("Brainstorm Prompt Sample (first 200 chars):")
    print(brainstorm_prompt[:200])
    
    # Test Content Gen Prompt
    research_data = "Some dummy research data"
    template_type = "guide"
    
    gen_prompt = CONTENT_GENERATION_PROMPT.format(
        research_data=research_data,
        template_type=template_type
    )
    print("\nContent Gen Prompt Sample (first 200 chars):")
    print(gen_prompt[:200])
    
    print("\nChecking for placeholders in Gen Prompt...")
    if "{template_type}" in gen_prompt:
        print("ERROR: {template_type} still in prompt!")
    else:
        print("SUCCESS: template_type formatted correctly.")

if __name__ == "__main__":
    asyncio.run(test_prompts())
