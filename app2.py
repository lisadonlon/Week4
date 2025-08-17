import streamlit as st
import os
import asyncio
import traceback
from agents import Agent, Runner, WebSearchTool, FileSearchTool
from fda_tool import FDAMedicalDeviceTool
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get configuration
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
vector_store_id = os.environ["vector_store_id"]

# Debug: Check OpenAI version and test client
import openai
print(f"OpenAI library version: {openai.__version__}")

try:
    test_client = openai.OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI client created successfully")
except Exception as e:
    print(f"❌ OpenAI client creation failed: {e}")
    st.error(f"OpenAI setup issue: {e}")
    st.stop()

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "use_web_search" not in st.session_state:
    st.session_state.use_web_search = True
if "use_file_search" not in st.session_state:
    st.session_state.use_file_search = True
if "use_fda_search" not in st.session_state:
    st.session_state.use_fda_search = False


def create_research_assistant():
    """Create agent with selected tools"""
    tools = []
    
    if st.session_state.use_web_search:
        tools.append(WebSearchTool())
        
    if st.session_state.use_file_search:
        tools.append(FileSearchTool(
            max_num_results=3,
            vector_store_ids=[vector_store_id],
        ))
        
    if st.session_state.use_fda_search:
        tools.append(FDAMedicalDeviceTool(debug_mode=False))
    
    instructions = """You are a medical device regulatory research assistant. Your role is to help users understand:

1. Medical device regulatory pathways and classifications
2. FDA database information (510k, PMA, recalls, adverse events)
3. Device specifications and intended use from uploaded documents
4. Regulatory compliance requirements

When responding:
- Always confirm device details with the user before searching FDA databases
- Provide structured, clear information with proper headings
- Highlight any safety concerns or recalls prominently
- Cite your sources (internal documents, FDA databases, web search)
- Ask clarifying questions when device information is unclear"""

    return Agent(
        name="Medical Device Research Assistant",
        instructions=instructions,
        model="gpt-4.1",
        tools=tools,
    )


async def get_research_response(question, history):
    """Process question with research assistant"""
    try:
        # Create agent
        research_assistant = create_research_assistant()
        
        # Build context from recent conversation
        context = ""
        if history:
            recent_messages = history[-3:]  # Last 3 exchanges
            context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
        
        # Combine context and question
        if context:
            full_prompt = f"Recent conversation:\n{context}\n\nCurrent question: {question}"
        else:
            full_prompt = question
        
        # Get response
        result = await Runner.run(research_assistant, full_prompt)
        return result.final_output
        
    except Exception as e:
        error_msg = f"Error processing your request: {str(e)}"
        st.error(error_msg)
        
        # Show error details in expander for debugging
        with st.expander("Error Details"):
            st.code(traceback.format_exc())
        
        return "I encountered an error processing your request. Please try rephrasing your question or check the error details above."


# Page configuration
st.set_page_config(
    page_title="Medical Device Research Assistant",
    page_icon="🏥",
    layout="wide"
)

# Main title
st.title("🏥 Medical Device Research Assistant")
st.write("Get regulatory information about medical devices from FDA databases and your uploaded documents.")

# Sidebar configuration
st.sidebar.title("Search Configuration")

# Tool selection
st.sidebar.subheader("Select Search Sources")
web_search = st.sidebar.checkbox("Web Search", value=st.session_state.use_web_search)
file_search = st.sidebar.checkbox("Document Search", value=st.session_state.use_file_search)
fda_search = st.sidebar.checkbox("FDA Database", value=st.session_state.use_fda_search)

# Update session state
st.session_state.use_web_search = web_search
st.session_state.use_file_search = file_search
st.session_state.use_fda_search = fda_search

# FDA database information
if st.session_state.use_fda_search:
    st.sidebar.subheader("FDA Database Info")
    st.sidebar.write("""
    **Available databases:**
    - **510(k)**: Device clearances
    - **PMA**: Premarket approvals  
    - **Recall**: Device recalls
    - **MAUDE**: Adverse events
    """)

# Vector store information
if st.session_state.use_file_search:
    st.sidebar.subheader("Document Search Info")
    st.sidebar.write(f"**Vector Store ID:** `{vector_store_id[:20]}...`")

# Validate configuration
if not (web_search or file_search or fda_search):
    st.sidebar.warning("⚠️ Please select at least one search source")

# Clear conversation
if st.sidebar.button("Clear Conversation"):
    st.session_state.messages = []
    st.rerun()

# Example queries
with st.sidebar.expander("💡 Example Questions"):
    st.markdown("""
    **Document Analysis:**
    - What medical devices are mentioned in my documents?
    - What is the intended use of the Everion device?
    
    **FDA Database Queries:**
    - Find FDA recalls for insulin pumps
    - What is the 510(k) status of robotic surgical systems?
    - Show adverse events for cardiac stents
    
    **General Research:**
    - What are the regulatory requirements for Class III devices?
    - Compare PMA vs 510(k) approval pathways
    """)

# Main chat interface
st.subheader("💬 Chat")

# Display conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input
user_question = st.chat_input("Ask about medical devices, regulations, or your documents...")

if user_question:
    # Validate tool selection
    if not (st.session_state.use_web_search or st.session_state.use_file_search or st.session_state.use_fda_search):
        st.error("Please select at least one search source in the sidebar.")
    else:
        # Add user message
        st.session_state.messages.append({"role": "user", "content": user_question})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_question)
        
        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Researching your question..."):
                response = asyncio.run(get_research_response(user_question, st.session_state.messages))
                st.markdown(response)
                
                # Add assistant response to history
                st.session_state.messages.append({"role": "assistant", "content": response})

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("🔬 **Medical Device Research Assistant**")
st.sidebar.markdown("Powered by OpenAI GPT-4.1 and FDA tools")

# Create debug directory if it doesn't exist
debug_dir = os.path.join(os.getcwd(), "debug")
if not os.path.exists(debug_dir):
    os.makedirs(debug_dir)
