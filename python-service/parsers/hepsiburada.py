async def parse_store(store_data):
    print(f"Processing Hepsiburada store: {store_data['name']}")
    # Add your Hepsiburada-specific parsing logic here
    api_info = store_data.get('api_connect_info', {})
    if api_info:
        # Process the store using API credentials
        print(f"Processing with API credentials: {api_info['store_id']}")
    return True
