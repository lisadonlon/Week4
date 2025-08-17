import openai
import os
import time
from typing import List
from fda_tool import FDAMedicalDeviceTool
import requests
from duckduckgo_search import DDGS

class Agent:
    def __init__(self, name: str, instructions: str, model: str = "gpt-4.1", tools: list = None):
        self.name = name
        self.instructions = instructions
        self.model = model
        self.tools = tools or []
        self.client = None
    
    def _get_openai_client(self):
        """Get OpenAI client, creating it if needed"""
        if self.client is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            
            # Create client with only the API key - no other parameters
            try:
                self.client = openai.OpenAI(api_key=api_key)
            except TypeError as e:
                if "proxies" in str(e):
                    # Fallback for older openai versions
                    raise Exception("Please update your OpenAI library: pip install openai --upgrade")
                raise e
        return self.client
    
    async def process(self, user_input: str) -> str:
        """Process user input with available tools"""
        tool_results = []
        
        try:
            # Step 1: Search vector store first (if available)
            vector_tool = self._find_tool_by_name("file_search")
            if vector_tool:
                try:
                    vector_result = vector_tool.run(user_input)
                    if vector_result and len(vector_result.strip()) > 20:
                        tool_results.append(f"## Internal Documents\n{vector_result}")
                except Exception as e:
                    tool_results.append(f"**Vector Store Error:** {str(e)}")
            
            # Step 2: Check if we should search FDA
            should_search_fda = self._needs_fda_search(user_input, tool_results)
            fda_tool = self._find_tool_by_name("fda_medical_device")
            
            if fda_tool and should_search_fda:
                search_query, database = self._get_fda_search_params(user_input, tool_results)
                try:
                    fda_result = fda_tool.run(search_query, database)
                    if fda_result:
                        tool_results.append(f"## FDA Database Results\n{fda_result}")
                except Exception as e:
                    tool_results.append(f"**FDA Search Error:** {str(e)}")
            
            # Step 3: Web search if requested
            if any(term in user_input.lower() for term in ["web search", "latest", "recent", "current"]):
                web_tool = self._find_tool_by_name("web_search")
                if web_tool:
                    try:
                        web_result = web_tool.run(user_input)
                        tool_results.append(f"## Web Search Results\n{web_result}")
                    except Exception as e:
                        tool_results.append(f"**Web Search Error:** {str(e)}")
            
            # Step 4: Generate final response
            return await self._generate_response(user_input, tool_results)
            
        except Exception as e:
            return f"I encountered an error processing your request: {str(e)}"
    
    def _find_tool_by_name(self, name: str):
        """Find tool by name attribute"""
        for tool in self.tools:
            if hasattr(tool, 'name') and tool.name == name:
                return tool
        return None
    
    def _needs_fda_search(self, user_input: str, results: List[str]) -> bool:
        """Determine if FDA search is needed"""
        combined_text = (user_input + " " + " ".join(results)).lower()
        
        fda_keywords = [
            "fda", "recall", "510k", "clearance", "approval", "pma",
            "medical device", "adverse event", "regulatory", "maude"
        ]
        
        return any(keyword in combined_text for keyword in fda_keywords)
    
    def _get_fda_search_params(self, user_input: str, results: List[str]) -> tuple:
        """Extract search query and database for FDA"""
        combined_text = user_input + " " + " ".join(results)
        
        # Look for specific devices
        device_keywords = ["everion", "biofourmis", "insulin pump", "pacemaker", "stent", "catheter"]
        search_query = "medical device"  # default
        
        for device in device_keywords:
            if device in combined_text.lower():
                search_query = device
                break
        
        # Determine database
        database = "all"  # default
        if "recall" in combined_text.lower():
            database = "recall"
        elif "510k" in combined_text.lower() or "clearance" in combined_text.lower():
            database = "510k"
        elif "pma" in combined_text.lower() or "approval" in combined_text.lower():
            database = "pma"
        elif "adverse" in combined_text.lower() or "event" in combined_text.lower():
            database = "event"
        
        return search_query, database
    
    async def _generate_response(self, user_input: str, tool_results: List[str]) -> str:
        """Generate final response using OpenAI"""
        if tool_results:
            context = "\n\n".join(tool_results)
            prompt = f"""User Question: {user_input}

Information Found:
{context}

Please provide a comprehensive, well-structured answer based on the information above. Use clear headings and highlight any important safety or regulatory information."""
        else:
            prompt = f"""User Question: {user_input}

No additional information was found from the search tools. Please provide the best answer you can and suggest what specific information the user might want to search for."""
        
        try:
            # Debug: Print what we're about to do
            print("🤖 Creating OpenAI client for response generation...")
            
            # Create client with explicit parameters only
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return "OpenAI API key not configured"
            
            # Try creating client with minimal, explicit parameters
            print("🔧 Attempting client creation...")
            try:
                # Use **only** the api_key parameter, nothing else
                client = openai.OpenAI(api_key=api_key)
                print("✅ OpenAI client created successfully")
            except Exception as client_error:
                print(f"❌ Client creation failed: {client_error}")
                return f"Failed to create OpenAI client: {client_error}"
            
            print("🚀 Making API request...")
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.instructions},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            print("✅ OpenAI response received successfully")
            return response.choices[0].message.content
            
        except Exception as e:
            error_details = str(e)
            print(f"❌ Error in _generate_response: {error_details}")
            
            # More detailed error reporting
            import traceback
            full_traceback = traceback.format_exc()
            print("Full traceback:")
            print(full_traceback)
            
            return f"Error generating response: {error_details}"


class Runner:
    @staticmethod
    async def run(agent: Agent, user_input: str):
        result = await agent.process(user_input)
        return type('Result', (), {'final_output': result})()


class WebSearchTool:
    def __init__(self):
        self.name = "web_search"
        self.description = "Search the web for current information using DuckDuckGo"
    
    def run(self, query: str) -> str:
        try:
            print(f"🦆 Searching DuckDuckGo for: {query}")
            
            # Search with DuckDuckGo
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                
                if not results:
                    return "No current web results found."
                
                # Format results
                formatted_results = []
                for result in results[:3]:  # Limit to top 3
                    title = result.get('title', 'No title')
                    snippet = result.get('body', 'No description')
                    url = result.get('href', '')
                    
                    formatted_results.append(f"**{title}**\n{snippet}\n*Source: {url}*")
                
                web_content = "\n\n".join(formatted_results)
                
                # Summarize with OpenAI
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    client = openai.OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": "Summarize these current web search results clearly and concisely. Highlight the most important and recent information."},
                            {"role": "user", "content": f"Query: {query}\n\nCurrent Web Results:\n{web_content}"}
                        ],
                        temperature=0.3,
                        max_tokens=600
                    )
                    return f"**Current Web Search Results (August 2025):**\n{response.choices[0].message.content}\n\n---\n**Sources:**\n{web_content}"
                else:
                    return f"**Current Web Results:**\n{web_content}"
                    
            except Exception as ddg_error:
                print(f"DuckDuckGo search failed: {ddg_error}")
                # Fallback to knowledge-based response
                return self._fallback_response(query)
            
        except Exception as e:
            print(f"❌ WebSearchTool error: {e}")
            return f"Web search error: {str(e)}"
    
    def _fallback_response(self, query: str) -> str:
        """Fallback to OpenAI knowledge when web search fails"""
        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return "Search temporarily unavailable"
            
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "Provide information based on your knowledge. Be clear that this is from your training data and may not reflect the most recent developments."},
                    {"role": "user", "content": f"Provide information about: {query}"}
                ],
                temperature=0.3,
                max_tokens=600
            )
            
            return f"**Knowledge Base Response:**\n{response.choices[0].message.content}\n\n*Note: Web search temporarily unavailable. This information is based on training data.*"
            
        except Exception as e:
            return f"Information temporarily unavailable: {str(e)}"


class FileSearchTool:
    def __init__(self, max_num_results: int = 3, vector_store_ids: List[str] = None):
        self.name = "file_search"
        self.description = "Search files in vector store"
        self.max_num_results = max_num_results
        self.vector_store_ids = vector_store_ids or []
    
    def run(self, query: str) -> str:
        try:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return "OpenAI API key not configured"
            
            print("📁 Creating OpenAI client for vector search...")
            try:
                client = openai.OpenAI(api_key=api_key)
                print("✅ FileSearch client created")
            except Exception as e:
                print(f"❌ FileSearch client creation failed: {e}")
                return f"Vector search client error: {e}"
            
            # Create temporary assistant for this search
            assistant = client.beta.assistants.create(
                name="Document Searcher",
                instructions="Search through the uploaded documents and provide relevant information. Be thorough but concise.",
                model="gpt-4.1",
                tools=[{"type": "file_search"}],
                tool_resources={
                    "file_search": {
                        "vector_store_ids": self.vector_store_ids
                    }
                }
            )
            
            # Create thread and message
            thread = client.beta.threads.create()
            
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=query
            )
            
            # Run the assistant
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id
            )
            
            # Wait for completion
            max_wait = 45
            start_time = time.time()
            
            while run.status in ['queued', 'in_progress']:
                if time.time() - start_time > max_wait:
                    raise Exception("Search timeout")
                time.sleep(2)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread.id,
                    run_id=run.id
                )
            
            # Get response
            if run.status == 'completed':
                messages = client.beta.threads.messages.list(
                    thread_id=thread.id,
                    order="desc"
                )
                
                for message in messages.data:
                    if message.role == 'assistant':
                        content = ""
                        for block in message.content:
                            if hasattr(block, 'text'):
                                content += block.text.value
                        
                        # Cleanup
                        try:
                            client.beta.assistants.delete(assistant.id)
                            client.beta.threads.delete(thread.id)
                        except:
                            pass
                        
                        return content if content else "No relevant documents found."
                
                return "No response from document search."
            else:
                return f"Document search failed: {run.status}"
                
        except Exception as e:
            print(f"❌ FileSearchTool error: {e}")
            return f"Vector store error: {str(e)}"
