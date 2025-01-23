import requests
import os
import cv2
import base64
import json
from multiprocessing import Queue
from datetime import datetime
from dotenv import load_dotenv
import logging
from bs4 import BeautifulSoup  # For parsing HTML responses

def initialize_environment():
    """Set up the environment and configure logging."""
    logging.basicConfig(
        level=logging.INFO,  # Set the log level to INFO or DEBUG for detailed logs
        format='%(asctime)s - %(levelname)s - %(message)s'  # Log format
    )
    logger = logging.getLogger(__name__)  # Use the module name as the logger's name
    return logger

# Initialize the logger globally
logger = initialize_environment()

# Load environment variables
load_dotenv("/home/user/Desktop/sort/a.env")

TOKEN = "TOKEN"
DASHBOARD_LINK = "DASHBOARD_LINK"

# Correct mapping dictionary
detection_types_mapping_dict = {
    "No_Gloves": 0,
    "No_Sleeves": 1,
    "No_Helmet": 2,  # Ensure the capitalization matches the detection labels
}

def prepare_image(frame, live_stream=False, encode_quality=50): 
    """Encodes the frame to a Base64 string for API transmission."""
    try:
        # Resize frame if live_stream is enabled
        if live_stream:
            frame = cv2.resize(frame, (960, 540))
        
        # Encode the frame as a PNG image
        success, buffer = cv2.imencode('.png', frame, [cv2.IMWRITE_PNG_COMPRESSION, encode_quality])
        if not success:
            raise ValueError("Image encoding failed.")

        # Convert the image to a Base64 string
        dashboard_img = base64.b64encode(buffer).decode()

        # Validate the Base64 string by decoding it back
        base64.b64decode(dashboard_img, validate=True)

        # Log success message
        logger.info("Image successfully encoded and validated as Base64.")
        
        # Optionally, write the Base64 string to a file for debugging
        with open("encoded_image.txt", "w") as file:
            file.write(dashboard_img)
            logger.info("Encoded Base64 string written to 'encoded_image.txt'.")

        return dashboard_img
    except Exception as e:
        logger.error(f"Error in prepare_image: {e}")
        raise



def accumulate_event(location_id, frame, detection_types, results_queue: Queue):
    """Accumulate event data and place it into the queue for processing."""
    if location_id == 0:
        location_id = 1

    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    unique_detection_types = set(detection_types)

    detections_list = []
    for detection in unique_detection_types:
        detection_id = detection_types_mapping_dict.get(detection)
        if detection_id is None:
            logger.warning(f"Detection type '{detection}' not found in mapping. Skipping.")
            continue
        detections_list.append({
            "type": detection_id,
            "details": detection.replace("_", " ").lower(),
        })

    payload = {
        "location_id": location_id,
        "date": str(date),
        "type": max([det["type"] for det in detections_list], default=1),
        "detections": detections_list,
        "image": prepare_image(frame),
    }

    results_without_image = {key: value for key, value in payload.items() if key != "image"}
    logger.info(f"Final Results for Queue (without image): {results_without_image}")
    results_queue.put(payload)

def parse_json_or_html(response):
    """
    Parse the response content as JSON or HTML.

    Args:
        response (requests.Response): The HTTP response object.

    Returns:
        dict: Parsed data or details of the HTML content.
    """
    try:
        # Try parsing as JSON
        return response.json()
    except json.JSONDecodeError:
        logger.warning("Response is not JSON. Attempting to parse as HTML.")
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        title = soup.title.string if soup.title else "No Title"
        return {"html": {"title": title, "content": soup.prettify()}}
    

def push_event(session, event_queue: Queue):
    """Push events to the dashboard."""
    while True:
        try:
            event = event_queue.get()
            if event is None:  # Check for the sentinel value to stop processing
                logger.info("Received sentinel value. Stopping push_event.")
                break

            headers = {
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            }

            response = session.post(DASHBOARD_LINK, json=event, headers=headers)
            response.raise_for_status()  # Raise an error for HTTP issues

            # Log success or handle parsing
            logger.info(f"Event pushed successfully: {response.status_code}")
            parsed_response = parse_json_or_html(response)
            logger.debug(f"Response from dashboard: {parsed_response}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error pushing event to dashboard: {e}")
            continue  # Retry or handle failure

    logger.info("push_event process finished.")
