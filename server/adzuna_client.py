import aiohttp
import asyncio
from typing import Optional, Dict, Any
import urllib.parse

class AdzunaClient:
    """
    Client for interacting with the Adzuna Jobs API
    Documentation: https://developer.adzuna.com/overview
    """
    
    def __init__(self, api_key: str, app_id: str):
        self.api_key = api_key
        self.app_id = app_id
        self.base_url = "https://api.adzuna.com/v1/api/jobs"
        self.country = "us"  # United States
        
    async def search_jobs(
        self, 
        keywords: str, 
        location: Optional[str] = None,
        results_per_page: int = 20,
        page: int = 1,
        sort_by: str = "relevance"
    ) -> Dict[str, Any]:
        """
        Search for jobs using the Adzuna API
        
        Args:
            keywords: Job search terms (required)
            location: Location to search in (optional)
            results_per_page: Number of results per page (max 50)
            page: Page number (starts at 1)
            sort_by: Sort order ('relevance', 'date', 'salary')
            
        Returns:
            Dictionary containing job results and metadata
        """
        
        # Build the search URL
        endpoint = f"{self.base_url}/{self.country}/search/{page}"
        
        # Build query parameters
        params = {
            'app_id': self.app_id,
            'app_key': self.api_key,
            'results_per_page': min(results_per_page, 50),  # Max 50 per API docs
            'what': keywords,
            'sort_by': sort_by
        }
        
        # Add location if provided
        if location:
            params['where'] = location
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        return self._process_job_results(data)
                    
                    elif response.status == 401:
                        raise Exception("Unauthorized: Check your Adzuna API credentials")
                    
                    elif response.status == 429:
                        raise Exception("Rate limit exceeded: Too many requests to Adzuna API")
                    
                    else:
                        error_text = await response.text()
                        raise Exception(f"Adzuna API error {response.status}: {error_text}")
                        
        except aiohttp.ClientError as e:
            raise Exception(f"Network error connecting to Adzuna API: {str(e)}")
        except Exception as e:
            raise Exception(f"Error searching jobs: {str(e)}")
    
    def _process_job_results(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process and clean the raw API response
        
        Args:
            raw_data: Raw response from Adzuna API
            
        Returns:
            Processed job data
        """
        processed_jobs = []
        
        for job in raw_data.get('results', []):
            processed_job = {
                'id': job.get('id', ''),
                'title': job.get('title', ''),
                'company': {
                    'display_name': job.get('company', {}).get('display_name', 'Company not specified')
                },
                'location': {
                    'display_name': self._format_location(job.get('location', {}))
                },
                'description': self._clean_description(job.get('description', '')),
                'created': job.get('created', ''),
                'redirect_url': job.get('redirect_url', ''),
                'salary_min': job.get('salary_min'),
                'salary_max': job.get('salary_max'),
                'contract_type': job.get('contract_type', ''),
                'category': job.get('category', {}).get('label', ''),
            }
            processed_jobs.append(processed_job)
        
        return {
            'jobs': processed_jobs,
            'count': raw_data.get('count', 0),
            'page': raw_data.get('page', 1),
            'results_per_page': len(processed_jobs)
        }
    
    def _format_location(self, location_data: Dict[str, Any]) -> str:
        """
        Format location data into a readable string
        """
        if not location_data:
            return "Location not specified"
            
        parts = []
        
        # Add area (city/region)
        if location_data.get('area'):
            for area in location_data['area']:
                if area not in parts:
                    parts.append(area)
        
        # Add display_name if available and not already included
        display_name = location_data.get('display_name', '')
        if display_name and display_name not in ' '.join(parts):
            parts = [display_name] + parts
            
        return ', '.join(parts) if parts else "Location not specified"
    
    def _clean_description(self, description: str) -> str:
        """
        Clean and format job description
        """
        if not description:
            return ""
            
        # Remove HTML tags (basic cleaning)
        import re
        description = re.sub(r'<[^>]+>', '', description)
        
        # Remove extra whitespace
        description = ' '.join(description.split())
        
        # Limit length for database storage
        if len(description) > 1000:
            description = description[:997] + "..."
            
        return description
    
    async def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific job
        
        Args:
            job_id: The job ID from Adzuna
            
        Returns:
            Detailed job information
        """
        endpoint = f"{self.base_url}/{self.country}/jobs/{job_id}"
        params = {
            'app_id': self.app_id,
            'app_key': self.api_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise Exception(f"Failed to get job details: {response.status}")
        except Exception as e:
            raise Exception(f"Error getting job details: {str(e)}")
    
    async def get_categories(self) -> Dict[str, Any]:
        """
        Get available job categories from Adzuna
        """
        endpoint = f"{self.base_url}/{self.country}/categories"
        params = {
            'app_id': self.app_id,
            'app_key': self.api_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        raise Exception(f"Failed to get categories: {response.status}")
        except Exception as e:
            raise Exception(f"Error getting categories: {str(e)}")

# Test function
async def test_adzuna_client():
    """
    Test function for the Adzuna client
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    api_key = os.getenv("ADZUNA_API_KEY")
    app_id = os.getenv("ADZUNA_APP_ID")
    
    if not api_key or not app_id:
        print("❌ Please set ADZUNA_API_KEY and ADZUNA_APP_ID environment variables")
        return
    
    client = AdzunaClient(api_key, app_id)
    
    try:
        print("🔍 Testing Adzuna API connection...")
        results = await client.search_jobs("software engineer", "San Francisco", results_per_page=5)
        
        print(f"✅ Found {results['count']} jobs")
        print(f"📄 Showing {len(results['jobs'])} results")
        
        for i, job in enumerate(results['jobs'][:3], 1):
            print(f"\n{i}. {job['title']}")
            print(f"   Company: {job['company']['display_name']}")
            print(f"   Location: {job['location']['display_name']}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_adzuna_client())