from setuptools import find_packages, setup

package_name = 'scv_monitor'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='doyoon-kim',
    maintainer_email='tnduaehowl37@gmail.com',
    description='관제 PC: ros_bridge, 관제 웹(Flask), webcam_node',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
        ],
    },
)
