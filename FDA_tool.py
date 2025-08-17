from typing import Any, Dict, List, Optional
import requests
from urllib.parse import quote
import streamlit as st
import traceback
import json

class FDAMedicalDeviceTool:
    """Tool for querying FDA medical device databases"""
    
    def __init__(self, debug_mode=False):
        self.name = "fda_medical_device"  # Consistent name for tool identification
        self.debug_mode = debug_mode
        self.base_url = "https://api.fda.gov/device"  # Add this missing line
    
    def _debug_print(self, level, message):
        """Print debug messages only if debug_mode is enabled"""
        if not self.debug_mode:
            return
            
        try:
            import streamlit as st
            if st.session_state.get('is_sidebar_debug', False):
                if level == "info":
                    st.sidebar.info(message)
                elif level == "success":
                    st.sidebar.success(message)
                elif level == "warning":
                    st.sidebar.warning(message)
                elif level == "error":
                    st.sidebar.error(message)
                elif level == "code":
                    st.sidebar.code(message)
        except:
            # Fall back to print if streamlit not available
            print(f"[{level.upper()}] {message}")
    
    def run(self, query: str, database: str = "all", limit: int = 5) -> str:
        """
        Main method called by the agent framework
        
        Args:
            query: The search query
            database: Which FDA database to search ("510k", "pma", "recall", "event", "registrationlisting", or "all")
            limit: Maximum number of results to return
            
        Returns:
            Formatted string with search results
        """
        # Print debug info only if in debug mode AND in sidebar context
        self._debug_print("info", f"🔍 FDA Tool Debug: Searching for '{query}' in '{database}' database with limit {limit}")
        
        try:
            if database == "all":
                # Search across multiple databases and combine results
                results = {}
                db_to_search = ["recall", "event", "510k", "pma"]  # Prioritize recall and event for "recent recalls" query
                
                for db in db_to_search:
                    try:
                        self._debug_print("info", f"🔍 FDA Tool Debug: Searching in {db} database...")
                        
                        db_results = self._search_database(query, db, limit=max(2, limit//2))
                        
                        if db_results and 'results' in db_results and db_results['results']:
                            self._debug_print("success", f"✅ Found {len(db_results['results'])} results in {db} database")
                            results[db] = db_results
                        else:
                            self._debug_print("warning", f"⚠️ No results found in {db} database")
                    except Exception as e:
                        self._debug_print("error", f"❌ Error searching {db} database: {str(e)}")
                        continue  # Skip failed searches in multi-search
                
                if results:
                    return self._format_multi_results(results)
                else:
                    return f"No results found in any FDA database for the query: '{query}'. Please try a different search term or check the FDA website directly at https://www.fda.gov/medical-devices"
            else:
                # Search a specific database
                self._debug_print("info", f"🔍 FDA Tool Debug: Searching for '{query}' in '{database}' database...")
                
                results = self._search_database(query, database, limit)
                
                if results and 'results' in results and results['results']:
                    self._debug_print("success", f"✅ Found {len(results['results'])} results in {database} database")
                    return self._format_results(results, database)
                else:
                    self._debug_print("warning", f"⚠️ No results found in {database} database")
                    return f"No results found in the FDA {database} database for the query: '{query}'. Please try a different search term."
                
        except Exception as e:
            error_msg = f"Error searching FDA database: {str(e)}"
            self._debug_print("error", f"❌ {error_msg}")
            return error_msg
    
    def _search_database(self, query: str, database: str, limit: int = 5) -> Dict[str, Any]:
        """Search a specific FDA database"""
        # Sanitize and optimize the query for FDA API
        safe_query = self._sanitize_query(query, database)
        
        # Build the FDA API endpoint URL
        endpoint = f"{self.base_url}/{database}.json"
        
        # Simple params
        params = {
            "search": safe_query,
            "limit": limit
        }
        
        # Debug: Print the actual request
        print(f"DEBUG: Making request to: {endpoint}")
        print(f"DEBUG: Search query: '{safe_query}'")
        
        try:
            # Make the API request
            response = requests.get(endpoint, params=params, timeout=10)
            
            print(f"DEBUG: Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                num_results = len(result.get('results', []))
                print(f"DEBUG: Found {num_results} results")
                return result
            else:
                print(f"DEBUG: Error response: {response.text[:200]}...")
                raise Exception(f"API error: {response.status_code}")
                    
        except Exception as e:
            print(f"DEBUG: Exception occurred: {e}")
            raise e
    
    def _sanitize_query(self, query: str, database: str) -> str:
        """Optimize query for FDA API search syntax"""
        query = query.strip()
        
        # Handle empty queries
        if not query:
            return "device"
        
        # For single words, just return as-is
        if len(query.split()) == 1:
            return query
        
        # For multi-word queries, use field-specific searches
        if database == "510k":
            return f"device_name:{query}"
        elif database == "recall":
            return f"product_description:{query}"
        elif database == "event":
            return f"device.brand_name:{query}"
        elif database == "pma":
            return query  # PMA doesn't always work well with field searches
        else:
            return query
    
    def _format_results(self, results: Dict[str, Any], db_type: str) -> str:
        """Format API results into readable markdown"""
        if not results or 'results' not in results or not results['results']:
            return f"No results found in the FDA {db_type} database for this query."
            
        formatted = f"## FDA {db_type.upper()} Database Results\n\n"
        
        if db_type == "510k":
            # Format 510(k) clearance results
            formatted += self._format_510k_results(results)
            
        elif db_type == "pma":
            # Format PMA (Premarket Approval) results
            formatted += self._format_pma_results(results)
            
        elif db_type == "recall":
            # Format recall results
            formatted += self._format_recall_results(results)
            
        elif db_type == "event":
            # Format MAUDE adverse event results
            formatted += self._format_event_results(results)
            
        elif db_type == "registrationlisting":
            # Format registration & listing results
            formatted += self._format_registration_results(results)
        
        formatted += f"\n\nSource: FDA {db_type.upper()} Database via api.fda.gov"
        return formatted
    
    def _format_multi_results(self, results_dict: Dict[str, Dict[str, Any]]) -> str:
        """Format results from multiple databases"""
        if not results_dict:
            return "No results found in FDA databases for this query."
            
        formatted = "# FDA Medical Device Database Results\n\n"
        
        for db_type, results in results_dict.items():
            if 'results' in results and results['results']:
                formatted += f"## {db_type.upper()} Database\n"
                
                if db_type == "510k":
                    items = results['results'][:2]  # Limit to top 2 for multi-search
                    for item in items:
                        device_name = item.get('device_name', 'Unknown Device')
                        decision_date = item.get('decision_date', 'Unknown Date')
                        manufacturer = self._get_applicant_name(item)
                        k_number = item.get('k_number', 'Unknown')
                        
                        formatted += f"- **{device_name}** (K{k_number})\n"
                        formatted += f"  - Manufacturer: {manufacturer}\n"
                        formatted += f"  - Clearance Date: {decision_date}\n\n"
                
                elif db_type == "pma":
                    items = results['results'][:2]
                    for item in items:
                        device_name = item.get('openfda', {}).get('device_name', ['Unknown Device'])[0] if item.get('openfda', {}).get('device_name') else 'Unknown Device'
                        approval_date = item.get('approval_date', 'Unknown Date')
                        applicant = item.get('applicant', 'Unknown Manufacturer')
                        pma_number = item.get('pma_number', 'Unknown')
                        
                        formatted += f"- **{device_name}** ({pma_number})\n"
                        formatted += f"  - Manufacturer: {applicant}\n"
                        formatted += f"  - Approval Date: {approval_date}\n\n"
                
                elif db_type == "recall":
                    items = results['results'][:2]
                    for item in items:
                        product = item.get('product_description', 'Unknown Product')
                        reason = item.get('reason_for_recall', 'Unknown Reason')
                        date = item.get('recall_initiation_date', 'Unknown Date')
                        
                        formatted += f"- **{product}**\n"
                        formatted += f"  - Recall Reason: {reason[:100]}...\n" if len(reason) > 100 else f"  - Recall Reason: {reason}\n"
                        formatted += f"  - Date Initiated: {date}\n\n"
                
                elif db_type == "event":
                    items = results['results'][:2]
                    for item in items:
                        device = item.get('device', [{}])[0].get('brand_name', 'Unknown Device') if item.get('device') and len(item.get('device')) > 0 else 'Unknown Device'
                        manufacturer = item.get('device', [{}])[0].get('manufacturer_d_name', 'Unknown Manufacturer') if item.get('device') and len(item.get('device')) > 0 else 'Unknown Manufacturer'
                        event_type = item.get('event_type', 'Unknown Event Type')
                        date = item.get('date_received', 'Unknown Date')
                        
                        formatted += f"- **{device}**\n"
                        formatted += f"  - Manufacturer: {manufacturer}\n"
                        formatted += f"  - Event Type: {event_type}\n"
                        formatted += f"  - Report Date: {date}\n\n"
        
        formatted += "\nSource: FDA Databases via api.fda.gov"
        return formatted
    
    def _format_510k_results(self, results: Dict[str, Any]) -> str:
        """Format 510(k) clearance results"""
        formatted = ""
        for item in results['results']:
            device_name = item.get('device_name', 'Unknown Device')
            decision_date = item.get('decision_date', 'Unknown Date')
            manufacturer = self._get_applicant_name(item)
            k_number = item.get('k_number', 'Unknown')
            product_code = item.get('product_code', 'Unknown')
            device_class = item.get('device_class', 'Unknown')
            
            # Get the predicate device info if available
            predicate = "Not specified"
            if 'predicates' in item and item['predicates']:
                predicate_k = item['predicates'][0].get('k_number', '')
                predicate_name = item['predicates'][0].get('device_name', '')
                if predicate_k and predicate_name:
                    predicate = f"K{predicate_k} - {predicate_name}"
            
            formatted += f"### {device_name} (K{k_number})\n"
            formatted += f"- **Manufacturer:** {manufacturer}\n"
            formatted += f"- **Clearance Date:** {decision_date}\n"
            formatted += f"- **Product Code:** {product_code}\n"
            formatted += f"- **Device Class:** {device_class}\n"
            formatted += f"- **Predicate Device:** {predicate}\n\n"
            
            # Include summary if available
            if 'summary' in item and item['summary']:
                summary = item['summary']
                if len(summary) > 300:
                    summary = summary[:300] + "..."
                formatted += f"**Summary:** {summary}\n\n"
            
            formatted += "---\n\n"
        
        return formatted
    
    def _format_pma_results(self, results: Dict[str, Any]) -> str:
        """Format PMA approval results"""
        formatted = ""
        for item in results['results']:
            # Extract device info from openfda if available
            device_name = "Unknown Device"
            if 'openfda' in item and 'device_name' in item['openfda'] and item['openfda']['device_name']:
                device_name = item['openfda']['device_name'][0]
            
            approval_date = item.get('approval_date', 'Unknown Date')
            applicant = item.get('applicant', 'Unknown Manufacturer')
            pma_number = item.get('pma_number', 'Unknown')
            product_code = item.get('product_code', 'Unknown')
            
            formatted += f"### {device_name} ({pma_number})\n"
            formatted += f"- **Manufacturer:** {applicant}\n"
            formatted += f"- **Approval Date:** {approval_date}\n"
            formatted += f"- **Product Code:** {product_code}\n"
            
            # Include expedited review info if available
            if 'expedited_review_flag' in item:
                expedited = "Yes" if item['expedited_review_flag'] else "No"
                formatted += f"- **Expedited Review:** {expedited}\n"
            
            formatted += "\n---\n\n"
        
        return formatted
    
    def _format_recall_results(self, results: Dict[str, Any]) -> str:
        """Format recall results"""
        formatted = ""
        for item in results['results']:
            product = item.get('product_description', 'Unknown Product')
            reason = item.get('reason_for_recall', 'Unknown Reason')
            date = item.get('recall_initiation_date', 'Unknown Date')
            manufacturer = item.get('recalling_firm', 'Unknown Manufacturer')
            classification = item.get('classification', 'Unknown')
            
            formatted += f"### {product}\n"
            formatted += f"- **Manufacturer:** {manufacturer}\n"
            formatted += f"- **Date Initiated:** {date}\n"
            formatted += f"- **Classification:** {classification}\n"
            formatted += f"- **Reason for Recall:** {reason}\n"
            
            # Add voluntary vs mandated info if available
            if 'voluntary_mandated' in item:
                voluntary = item['voluntary_mandated']
                formatted += f"- **Type:** {voluntary}\n"
            
            # Add status if available
            if 'status' in item:
                status = item['status']
                formatted += f"- **Status:** {status}\n"
            
            formatted += "\n---\n\n"
        
        return formatted
    
    def _format_event_results(self, results: Dict[str, Any]) -> str:
        """Format MAUDE adverse event results"""
        formatted = ""
        for item in results['results']:
            # Device info is nested in a list
            device = {}
            if 'device' in item and item['device']:
                device = item['device'][0]
            
            device_name = device.get('brand_name', 'Unknown Device')
            manufacturer = device.get('manufacturer_d_name', 'Unknown Manufacturer')
            
            event_type = item.get('event_type', 'Unknown Event Type')
            date = item.get('date_received', 'Unknown Date')
            
            formatted += f"### {device_name} Adverse Event\n"
            formatted += f"- **Manufacturer:** {manufacturer}\n"
            formatted += f"- **Event Type:** {event_type}\n"
            formatted += f"- **Report Date:** {date}\n"
            
            # Add report source if available
            if 'source_type' in item:
                source = item['source_type']
                formatted += f"- **Report Source:** {source}\n"
            
            # Add device problem if available
            if 'device_problem' in item and item['device_problem']:
                problems = ", ".join(item['device_problem'])
                formatted += f"- **Device Problems:** {problems}\n"
            
            # Add patient outcome if available
            if 'patient' in item and item['patient'] and 'sequence_number_outcome' in item['patient'][0]:
                outcomes = ", ".join(item['patient'][0]['sequence_number_outcome'])
                formatted += f"- **Patient Outcomes:** {outcomes}\n"
            
            # Add MDR text if available
            if 'mdr_text' in item and item['mdr_text']:
                for text_entry in item['mdr_text']:
                    if text_entry.get('text_type_code') == 'D':  # Description of event
                        description = text_entry.get('text', 'No description available')
                        if len(description) > 300:
                            description = description[:300] + "..."
                        formatted += f"\n**Event Description:** {description}\n"
            
            formatted += "\n---\n\n"
        
        return formatted
    
    def _format_registration_results(self, results: Dict[str, Any]) -> str:
        """Format registration & listing results"""
        formatted = ""
        for item in results['results']:
            name = item.get('name', 'Unknown Company')
            reg_num = item.get('registration_number', 'Unknown')
            address = item.get('address_line_1', '')
            city = item.get('city', '')
            state = item.get('state', '')
            country = item.get('country_code', '')
            
            formatted += f"### {name} (Reg# {reg_num})\n"
            formatted += f"- **Address:** {address}, {city}, {state}, {country}\n"
            
            # Add establishment type if available
            if 'establishment_type' in item:
                est_type = item['establishment_type']
                formatted += f"- **Establishment Type:** {est_type}\n"
            
            # Add product codes if available
            if 'products' in item and item['products']:
                product_codes = [p.get('product_code', '') for p in item['products']]
                unique_codes = list(set(filter(None, product_codes)))
                if unique_codes:
                    formatted += f"- **Product Codes:** {', '.join(unique_codes)}\n"
            
            formatted += "\n---\n\n"
        
        return formatted
    
    def _get_applicant_name(self, item: Dict[str, Any]) -> str:
        """Extract applicant name from various possible fields"""
        # Different FDA endpoints use different field names for manufacturer
        for field in ['applicant', 'owner_operator', 'manufacturer']:
            if field in item and item[field]:
                return item[field]
        return "Unknown Manufacturer"
